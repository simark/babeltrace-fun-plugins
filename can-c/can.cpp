#include <babeltrace2/babeltrace.h>
#include <cassert>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <functional>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include <dbcmodel.h>
#include <dbcreader.h>

BT_PLUGIN_MODULE();

BT_PLUGIN(can);
BT_PLUGIN_DESCRIPTION("CAN format");
BT_PLUGIN_AUTHOR("Simon Marchi, Gabriel-Andrew Pollo-Guilbert");
BT_PLUGIN_LICENSE("GPL");

struct FILE_closer {
	void operator() (FILE *f) {
		if (f) {
			fclose(f);
		}
	}
};

using file_unique_ptr = std::unique_ptr<FILE, FILE_closer>;

static file_unique_ptr
fopen_unique(const char *pathname, const char *mode) {
	return file_unique_ptr(fopen(pathname, mode));
}

struct dbc_freeer {
	void operator() (dbc_t *d) {
		if (d) {
			dbc_free(d);
		}
	}
};

using dbc_unique_ptr = std::unique_ptr<dbc_t, dbc_freeer>;

static dbc_unique_ptr
dbc_read_file_unique(const char *path) {
	return dbc_unique_ptr(dbc_read_file((char *) path));
}

template <typename T, void (*put_ref_func) (const T *)>
struct bt_object_put_reffer {
	void operator() (T *obj) {
		if (obj) {
			put_ref_func(obj);
		}
	}
};

#define BT_OBJ_REF(name) \
	using name##_put_reffer = bt_object_put_reffer<name, name##_put_ref>; \
	using name##_ref = std::unique_ptr<name, name##_put_reffer>;

BT_OBJ_REF(bt_clock_class)
BT_OBJ_REF(bt_trace_class)
BT_OBJ_REF(bt_stream_class)
BT_OBJ_REF(bt_event_class)
BT_OBJ_REF(bt_field_class)
BT_OBJ_REF(bt_trace)
BT_OBJ_REF(bt_stream)
BT_OBJ_REF(bt_message)

struct can_source_data;

struct can_port_data {
	can_port_data(can_source_data *source_data, std::string &&trace_path)
	: source_data(source_data), trace_path(std::move(trace_path))
	{}

	can_source_data *source_data;
	std::string trace_path;
};

struct can_iter_data {
	can_iter_data (can_port_data *port_data)
	: port_data(port_data)
	{}

	can_port_data *port_data;
	file_unique_ptr trace_file;
	enum class can_iter_state {
		starting,
		reading,
		finishing,
		done,
	} state = can_iter_state::starting;

	bt_trace_ref trace;
	bt_stream_ref stream;
};

struct can_message {
	std::map<uint32_t, bt_event_class_ref> event_classes;

	const signal_t *multiplexor = NULL;
};

struct can_source_data {
	std::vector<std::unique_ptr<can_port_data>> ports_data;

	std::map<uint32_t, can_message> messages;

	dbc_unique_ptr dbc;

	bt_clock_class_ref clock_class;
	bt_trace_class_ref trace_class;
	bt_stream_class_ref stream_class;
	bt_event_class_ref unknown_event_class;
};

static bt_component_class_message_iterator_init_method_status
can_iter_init(bt_self_message_iterator *message_iterator,
		bt_self_component_source *self_component,
		bt_self_component_port_output *port_output)
{
	bt_self_component_port *port =
		bt_self_component_port_output_as_self_component_port(port_output);
	can_port_data *port_data = (can_port_data *) bt_self_component_port_get_data(port);
	std::unique_ptr<can_iter_data> iter_data = std::make_unique<can_iter_data>(port_data);

	const char *trace_path = port_data->trace_path.c_str();
	iter_data->trace_file = fopen_unique(trace_path, "rb");
	if (!iter_data->trace_file) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_MESSAGE_ITERATOR(
			message_iterator, "unable to open file `%s` :(", trace_path);
		return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_INIT_METHOD_STATUS_ERROR;
	}

	iter_data->trace.reset(bt_trace_create(iter_data->port_data->source_data->trace_class.get()));
	if (!iter_data->trace) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_MESSAGE_ITERATOR(
			message_iterator, "failed to create trace :(", trace_path);
		return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_INIT_METHOD_STATUS_MEMORY_ERROR;
	}

	iter_data->stream.reset(bt_stream_create(iter_data->port_data->source_data->stream_class.get(), iter_data->trace.get()));
	if (!iter_data->stream) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_MESSAGE_ITERATOR(
			message_iterator, "failed to create stream :(", trace_path);
		return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_INIT_METHOD_STATUS_MEMORY_ERROR;
	}

	bt_self_message_iterator_set_data(message_iterator, iter_data.release());

	return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_INIT_METHOD_STATUS_OK;
}

static bt_component_class_message_iterator_next_method_status
can_iterator_next_starting(bt_self_message_iterator *message_iterator,
		bt_message_array_const msgs,
		uint64_t capacity, uint64_t *count)
{
	can_iter_data *iter_data =
		(can_iter_data *) bt_self_message_iterator_get_data(message_iterator);

	assert(capacity >= 1);

	bt_message_ref stream_beg_msg(
		bt_message_stream_beginning_create(
			message_iterator, iter_data->stream.get()));
	if (!stream_beg_msg) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_MESSAGE_ITERATOR(
			message_iterator, "failed to create message :(");
		return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_MEMORY_ERROR;
	}

	msgs[0] = stream_beg_msg.release();

	*count = 1;

	iter_data->state = can_iter_data::can_iter_state::reading;

	return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_OK;
}

static bt_component_class_message_iterator_next_method_status
can_iterator_next_reading(bt_self_message_iterator *message_iterator,
		bt_message_array_const msgs,
		uint64_t capacity, uint64_t *count)
{
	can_iter_data *iter_data =
		(can_iter_data *) bt_self_message_iterator_get_data(message_iterator);
	FILE *trace_file = iter_data->trace_file.get();
	uint8_t data[16];

	int ret = fread(data, sizeof(data), 1, trace_file);
	if (ret != 1) {
		if (ferror(trace_file)) {
			BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_MESSAGE_ITERATOR(
				message_iterator, "failed to read from trace file :(");
			return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_ERROR;
		}

		if (feof(trace_file)) {
			return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_END;
		}
	}

	bt_message_ref event_msg(bt_message_event_create_with_default_clock_snapshot(message_iterator,
		iter_data->port_data->source_data->unknown_event_class.get(),
		iter_data->stream.get(), 1));

	if (!event_msg) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_MESSAGE_ITERATOR(
			message_iterator, "failed to create message :(");
		return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_MEMORY_ERROR;
	}

	bt_event *event = bt_message_event_borrow_event(event_msg.get());
	bt_field *payload = bt_event_borrow_payload_field(event);

	for (int i = 0; i < 9; i++) {
		bt_field *f = bt_field_structure_borrow_member_field_by_index(payload, i);
		bt_field_real_set_value(f, 0);
	}

	msgs[0] = event_msg.release();
	*count = 1;

	static int n = 0;
	printf("Read some bytes %d\n", n);
	n++;

	return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_OK;
}

static bt_component_class_message_iterator_next_method_status
can_iterator_next_finishing(bt_self_message_iterator *message_iterator,
		bt_message_array_const msgs,
		uint64_t capacity, uint64_t *count)
{
	can_iter_data *iter_data =
		(can_iter_data *) bt_self_message_iterator_get_data(message_iterator);

	assert(capacity >= 1);

	bt_message_ref stream_end_msg(
		bt_message_stream_end_create(
			message_iterator, iter_data->stream.get()));
	if (!stream_end_msg) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_MESSAGE_ITERATOR(
			message_iterator, "failed to create message :(");
		return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_MEMORY_ERROR;
	}

	msgs[0] = stream_end_msg.release();

	*count = 1;

	iter_data->state = can_iter_data::can_iter_state::done;

	return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_OK;
}

static bt_component_class_message_iterator_next_method_status
can_iterator_next(bt_self_message_iterator *message_iterator,
		bt_message_array_const msgs,
		uint64_t capacity, uint64_t *count)
{
	can_iter_data *iter_data =
		(can_iter_data *) bt_self_message_iterator_get_data(message_iterator);

	switch (iter_data->state) {
	case can_iter_data::can_iter_state::starting:
		return can_iterator_next_starting(message_iterator, msgs, capacity, count);
	case can_iter_data::can_iter_state::reading:
		return can_iterator_next_reading(message_iterator, msgs, capacity, count);
	case can_iter_data::can_iter_state::finishing:
		return can_iterator_next_finishing(message_iterator, msgs, capacity, count);
	case can_iter_data::can_iter_state::done:
		return 	BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_END;
	default:
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_MESSAGE_ITERATOR(message_iterator,
        		"unexpected iter_data state value :(");
		return BT_COMPONENT_CLASS_MESSAGE_ITERATOR_NEXT_METHOD_STATUS_ERROR;
	}
}

static bt_component_class_init_method_status
can_source_create_ports_from_inputs(
		bt_self_component_source *self_component_source,
		const bt_value *params,
		can_source_data *source_data)
{
	bt_self_component *self_component =
		bt_self_component_source_as_self_component(self_component_source);

	const bt_value *inputs_value =
		bt_value_map_borrow_entry_value_const(params, "inputs");
	if (!inputs_value) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        		"missing `inputs` params entry :(");
		return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
	}

	if (bt_value_get_type(inputs_value) != BT_VALUE_TYPE_ARRAY) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        		"`inputs` param is not an array :(");
		return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
	}

	for (uint64_t inputs_i = 0; inputs_i < bt_value_array_get_length(inputs_value); inputs_i++) {
		const bt_value *input_value =
			bt_value_array_borrow_element_by_index_const(inputs_value, inputs_i);

		if (bt_value_get_type(input_value) != BT_VALUE_TYPE_STRING) {
			BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        			"`inputs[%" PRIu64  "]` param is not a string :(", inputs_i);
			return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
		}

		const char *path = bt_value_string_get(input_value);
		std::unique_ptr<can_port_data> port_data = std::make_unique<can_port_data>(source_data, path);

		bt_self_component_add_port_status add_port_status =
			bt_self_component_source_add_output_port(
				self_component_source, "the-port", port_data.get(), NULL);
		if (add_port_status != BT_SELF_COMPONENT_ADD_PORT_STATUS_OK) {
			BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
				"failed to add output port :(");
			return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
		}

		source_data->ports_data.push_back(std::move(port_data));
	}

	return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK;
}

static bt_component_class_init_method_status
create_trace_class_from_databases(
		bt_self_component *self_component,
		const bt_value *params,
		can_source_data *source_data)
{
	const bt_value *databases_value =
		bt_value_map_borrow_entry_value_const(params, "databases");
	if (!databases_value) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        		"missing `databases` params entry :(");
		return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
	}

	if (bt_value_get_type(databases_value) != BT_VALUE_TYPE_ARRAY) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        		"`databases` param is not an array :(");
		return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
	}

	source_data->clock_class.reset(bt_clock_class_create(self_component));
	if (!source_data->clock_class) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        		"failed to create clock class :(");
		return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
	}

	bt_clock_class_set_frequency(source_data->clock_class.get(), 1000);

	source_data->trace_class.reset(bt_trace_class_create(self_component));
	if (!source_data->trace_class) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        		"failed to create trace class :(");
		return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
	}

	source_data->stream_class.reset(bt_stream_class_create(source_data->trace_class.get()));
	if (!source_data->stream_class) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        		"failed to create stream class :(");
		return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
	}

	bt_stream_class_set_default_clock_class_status set_default_cc_status;
	set_default_cc_status = bt_stream_class_set_default_clock_class(
		source_data->stream_class.get(),
		source_data->clock_class.get());
	if (set_default_cc_status != BT_STREAM_CLASS_SET_DEFAULT_CLOCK_CLASS_STATUS_OK) {
		return (bt_component_class_init_method_status) set_default_cc_status;
	}

	bt_stream_class_set_name_status sc_set_name_status;
	sc_set_name_status = bt_stream_class_set_name(source_data->stream_class.get(), "can");
	if (sc_set_name_status != BT_STREAM_CLASS_SET_NAME_STATUS_OK) {
		return (bt_component_class_init_method_status) sc_set_name_status;
	}

	{
		source_data->unknown_event_class.reset(bt_event_class_create(source_data->stream_class.get()));
		if (!source_data->unknown_event_class) {
			BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
				"failed to create event class :(");
			return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
		}

		bt_event_class_set_name_status ec_set_name_status;
		ec_set_name_status = bt_event_class_set_name(source_data->unknown_event_class.get(), "UNKNOWN");
		if (ec_set_name_status != BT_EVENT_CLASS_SET_NAME_STATUS_OK) {
			return (bt_component_class_init_method_status) ec_set_name_status;
		}

		bt_trace_class *tc = source_data->trace_class.get();
		bt_field_class_ref payload(bt_field_class_structure_create(tc));
		if (!payload) {
			BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
				"failed to create struct field class :(");
			return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
		}

		// TODO: this should be an integer.
		bt_field_class_ref id(bt_field_class_real_create(tc));
		if (!id) {
			BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
				"failed to create real field class :(");
			return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
		}

		bt_field_class_structure_append_member_status append_member_status;
		append_member_status = bt_field_class_structure_append_member(
			payload.get(), "id", id.get());
		if (append_member_status != BT_FIELD_CLASS_STRUCTURE_APPEND_MEMBER_STATUS_OK) {
			return (bt_component_class_init_method_status) append_member_status;
		}

		// TODO: this should probably be an array of uint8_t.
		for (int i = 0; i < 8; i++) {
			bt_field_class_ref byte(bt_field_class_real_create(tc));
			if (!byte) {
				BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
					"failed to create real field class :(");
				return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
			}

			std::stringstream name;
			name << "byte " << i;

			bt_field_class_structure_append_member_status append_member_status;
			append_member_status = bt_field_class_structure_append_member(
				payload.get(), name.str().c_str(), byte.get());
			if (append_member_status != BT_FIELD_CLASS_STRUCTURE_APPEND_MEMBER_STATUS_OK) {
				return (bt_component_class_init_method_status) append_member_status;
			}
		}

		bt_event_class_set_field_class_status set_fc_status;
		set_fc_status = bt_event_class_set_payload_field_class(
			source_data->unknown_event_class.get(), payload.get());
		if (set_fc_status != BT_EVENT_CLASS_SET_FIELD_CLASS_STATUS_OK) {
			return (bt_component_class_init_method_status) set_fc_status;
		}
	}


	for (uint64_t db_i = 0; db_i < bt_value_array_get_length(databases_value); db_i++) {
		const bt_value *database_value =
			bt_value_array_borrow_element_by_index_const(databases_value, db_i);

		if (bt_value_get_type(database_value) != BT_VALUE_TYPE_STRING) {
			BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        			"`databases[%" PRIu64  "]` param is not a string :(", db_i);
			return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
		}

		const char *dbc_path = bt_value_string_get(database_value);
		source_data->dbc = dbc_read_file_unique(dbc_path);
		if (!source_data->dbc) {
			BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        			"failed to open database file `%s`", dbc_path);
			return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
		}

		for (message_list_t *msg_node = source_data->dbc->message_list;
				msg_node; msg_node = msg_node->next) {
			const message_t * const msg = msg_node->message;
			const signal_t *muxer_signal = NULL;

			// Signals always present.
			std::vector<signal_t *> non_muxed_signals;

			// Muxer value to list of muxed signals.
			std::map<uint32_t, std::vector<signal_t *>> muxed_signals;

			for (signal_list_t *sig_node = msg->signal_list; sig_node;
					sig_node = sig_node->next) {
				signal_t *sig = sig_node->signal;

				if (sig->mux_type == m_multiplexor) {
					if (muxer_signal) {
						BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(
							self_component, "i don't support multiple multiplexors yet :(");
						return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
					}

					muxer_signal = sig;

					non_muxed_signals.push_back(sig);
				} else if (sig->mux_type == m_multiplexed) {
					auto ret = muxed_signals.emplace(std::make_pair(sig->mux_value, std::vector<signal_t *>()));

					ret.first->second.push_back(sig);
				} else {
					// not multiplexed
					non_muxed_signals.push_back(sig);
				}
			}

			auto create_members_for_signals = [](
					bt_field_class *payload, const std::vector<signal_t *> &signals,
					bt_trace_class *tc, bt_self_component *self_component)
						-> bt_component_class_init_method_status {
				for (signal_t *sig : signals) {
					bt_field_class *member = bt_field_class_real_create(tc);
					if (!member) {
						BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
							"failed to create real field class :(");
						return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
					}

					bt_field_class_structure_append_member_status append_member_status;
					append_member_status = bt_field_class_structure_append_member(
						payload, sig->name, member);
					if (append_member_status != BT_FIELD_CLASS_STRUCTURE_APPEND_MEMBER_STATUS_OK) {
						return (bt_component_class_init_method_status) append_member_status;
					}
				}

				return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK;
			};

			can_message &can_msg = source_data->messages[msg->id];
			if (muxer_signal) {
				if (muxed_signals.empty()) {
					BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(
						self_component, "multiplexor signal but no multiplexed signals :(");
					return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
				}

				can_msg.multiplexor = muxer_signal;

				for (auto item : muxed_signals) {
					bt_event_class_ref event_class(bt_event_class_create(source_data->stream_class.get()));
					if (!event_class) {
						BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
							"failed to create event class :(");
						return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
					}

					bt_event_class_set_name_status ec_set_name_status;
					ec_set_name_status = bt_event_class_set_name(event_class.get(), msg->name);
					if (ec_set_name_status != BT_EVENT_CLASS_SET_NAME_STATUS_OK) {
						return (bt_component_class_init_method_status) ec_set_name_status;
					}

					bt_trace_class *tc = source_data->trace_class.get();
					bt_field_class_ref payload(bt_field_class_structure_create(tc));
					if (!payload) {
						BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
							"failed to create struct field class :(");
						return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
					}

					bt_component_class_init_method_status status;
					status = create_members_for_signals(
						payload.get(), non_muxed_signals, tc, self_component);
					if (status != BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK) {
						return status;
					}

					status = create_members_for_signals(
						payload.get(), item.second, tc, self_component);
					if (status != BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK) {
						return status;
					}

					bt_event_class_set_field_class_status set_fc_status;
					set_fc_status = bt_event_class_set_payload_field_class(
						event_class.get(), payload.get());
					if (set_fc_status != BT_EVENT_CLASS_SET_FIELD_CLASS_STATUS_OK) {
						return (bt_component_class_init_method_status) set_fc_status;
					}

					can_msg.event_classes[item.first] = std::move(event_class);
				}
			} else {
				bt_event_class_ref event_class(bt_event_class_create(source_data->stream_class.get()));
				if (!event_class) {
					BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
						"failed to create event class :(");
					return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
				}

				bt_event_class_set_name_status ec_set_name_status;
				ec_set_name_status = bt_event_class_set_name(event_class.get(), msg->name);
				if (ec_set_name_status != BT_EVENT_CLASS_SET_NAME_STATUS_OK) {
					return (bt_component_class_init_method_status) ec_set_name_status;
				}

				bt_trace_class *tc = source_data->trace_class.get();
				bt_field_class_ref payload(bt_field_class_structure_create(tc));
				if (!payload) {
					BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
						"failed to create struct field class :(");
					return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_MEMORY_ERROR;
				}

				bt_component_class_init_method_status status;
				status = create_members_for_signals(
					payload.get(), non_muxed_signals, tc, self_component);
				if (status != BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK) {
					return status;
				}

				bt_event_class_set_field_class_status set_fc_status;
				set_fc_status = bt_event_class_set_payload_field_class(
					event_class.get(), payload.get());
				if (set_fc_status != BT_EVENT_CLASS_SET_FIELD_CLASS_STATUS_OK) {
					return (bt_component_class_init_method_status) set_fc_status;
				}

				can_msg.event_classes[0] = std::move(event_class);
			}
  		}
	}

	return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK;
}

static bt_component_class_init_method_status
can_source_init (bt_self_component_source *self_component_source,
		const bt_value *params, void *init_method_data)
{
	bt_self_component *self_component =
		bt_self_component_source_as_self_component(self_component_source);
	bt_component_class_init_method_status status;

	if (bt_value_get_type(params) != BT_VALUE_TYPE_MAP) {
		BT_CURRENT_THREAD_ERROR_APPEND_CAUSE_FROM_COMPONENT(self_component,
        		"params is not a map :(");
		return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_ERROR;
	}

	std::unique_ptr<can_source_data> source_data = std::make_unique<can_source_data>();

	status = can_source_create_ports_from_inputs(
		self_component_source, params, source_data.get());
	if (status != BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK) {
		return status;
	}

	status = create_trace_class_from_databases(
		self_component, params, source_data.get());
	if (status != BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK) {
		return status;
	}

	bt_self_component_set_data(self_component, source_data.release());

	return BT_COMPONENT_CLASS_INIT_METHOD_STATUS_OK;
}

static void
can_source_fini(bt_self_component_source *self_component_source)
{
	bt_self_component *self_component =
		bt_self_component_source_as_self_component(self_component_source);
	std::unique_ptr<can_source_data> source_data
		((can_source_data *) bt_self_component_get_data(self_component));
}

BT_PLUGIN_SOURCE_COMPONENT_CLASS(CANSource, can_iterator_next);
BT_PLUGIN_SOURCE_COMPONENT_CLASS_INIT_METHOD(CANSource, can_source_init);
BT_PLUGIN_SOURCE_COMPONENT_CLASS_FINALIZE_METHOD(CANSource, can_source_fini);
BT_PLUGIN_SOURCE_COMPONENT_CLASS_MESSAGE_ITERATOR_INIT_METHOD(CANSource, can_iter_init);