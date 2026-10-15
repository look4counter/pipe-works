from contextvars import copy_context
from io import StringIO
import logging
import pickle
from threading import Event, Thread
import unittest
from unittest.mock import patch

from pipeworks import remote_logging as relay


class RemoteLoggingTests(unittest.TestCase):
    def route(self, level=logging.DEBUG, **settings):
        sent = []
        policy = {"root": level, "loggers": {}, "disable": 0, **settings}
        route = relay.LogRoute(sent.append, Event(), policy, "pipeline", "run-1")
        return route, sent

    def record(self, name="app.worker", level=logging.INFO, msg="message", args=()):
        return logging.LogRecord(name, level, __file__, 17, msg, args, None, "work")

    def test_policy_uses_nearest_named_level_and_exact_disabled_state(self):
        route, sent = self.route(logging.WARNING, loggers={
            "app": {"level": logging.DEBUG, "disabled": True},
            "app.quiet": {"level": logging.ERROR, "disabled": False},
        })
        for name, level in [("other", logging.INFO), ("app", logging.ERROR),
                            ("app.worker", logging.DEBUG), ("app.quiet.child", logging.WARNING)]:
            route.emit(self.record(name, level))
        self.assertEqual([(data["name"], data["levelno"]) for _, data in sent], [("app.worker", logging.DEBUG)])

    def test_message_exception_origin_and_safe_extras_round_trip(self):
        route, sent = self.route()
        try:
            raise ValueError("failure details")
        except ValueError:
            import sys
            record = self.record(msg="value=%s", args=(object(),))
            record.exc_info = sys.exc_info()
            record.unserializable = lambda: None
            record.tags = {"count": 2}
            route.emit(record)
        kind, data = pickle.loads(pickle.dumps(sent[0]))
        self.assertEqual(kind, "log")
        self.assertIn("value=", data["msg"])
        self.assertIn("ValueError: failure details", data["exc_text"])
        self.assertIsNone(data["exc_info"])
        self.assertEqual(data["created"], record.created)
        self.assertEqual(data["pathname"], record.pathname)
        self.assertEqual(data["thread"], record.thread)
        self.assertEqual(data["pipeworks_pipeline"], "pipeline")
        self.assertEqual(data["pipeworks_execution_id"], "run-1")
        self.assertEqual(data["tags"], {"count": 2})
        self.assertIsInstance(data["unserializable"], str)

    def test_receiver_respects_logger_and_handler_levels_and_filters(self):
        route, sent = self.route()
        route.emit(self.record("relay.unit", logging.DEBUG))
        logger = logging.getLogger("relay.unit")
        previous = logger.level, logger.propagate, logger.handlers[:]
        output = StringIO()
        handler = logging.StreamHandler(output)
        handler.setLevel(logging.INFO)
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        try:
            relay.dispatch_record(sent[0][1])
            self.assertEqual(output.getvalue(), "")
            handler.setLevel(logging.DEBUG)
            relay.dispatch_record(sent[0][1])
            self.assertEqual(output.getvalue(), "message\n")
            output.seek(0)
            output.truncate()
            logger.setLevel(logging.INFO)
            relay.dispatch_record(sent[0][1])
            self.assertEqual(output.getvalue(), "")
            logger.setLevel(logging.DEBUG)
            handler.addFilter(lambda record: False)
            relay.dispatch_record(sent[0][1])
            self.assertEqual(output.getvalue(), "")
        finally:
            logger.setLevel(previous[0])
            logger.propagate, logger.handlers = previous[1:]

    def test_print_adapter_combines_fragments_flushes_and_bounds_buffers(self):
        route, sent = self.route()
        writer = relay.PrintAdapter(route)
        self.assertEqual(writer("a "), 2)
        writer("b\npartial")
        writer.flush()
        writer("x" * (writer.limit + 5))
        writer.close()
        writer("after close\n")
        messages = [data["msg"] for _, data in sent]
        self.assertEqual(messages[:2], ["a b", "partial"])
        self.assertEqual(messages[2:], ["x" * writer.limit, "xxxxx"])
        self.assertTrue(all(data["levelno"] == logging.DEBUG for _, data in sent))
        self.assertTrue(all(data["name"] == "pipeworks.user_output" for _, data in sent))

    def test_print_buffers_are_separate_per_worker_and_closed_before_final_response(self):
        route, sent = self.route()
        writer = relay.PrintAdapter(route)
        first_written, second_written = Event(), Event()

        def first():
            writer("first")
            first_written.set()
            second_written.wait(2)
            writer(" line\n")

        def second():
            first_written.wait(2)
            writer("second\n")
            second_written.set()

        threads = [Thread(target=first), Thread(target=second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        writer("tail")
        writer.close()
        route.close()
        sent.append(("ok", None))
        route.emit(self.record())
        self.assertEqual([data["msg"] for _, data in sent[:-1]], ["second", "first line", "tail"])
        self.assertEqual(sent[-1], ("ok", None))

    def test_route_context_isolated_restored_and_remote_records_not_relayed(self):
        first, a = self.route()
        second, b = self.route(logging.ERROR)
        handler = relay.RelayHandler()
        with relay.use_route(first):
            context = copy_context()
            with relay.use_route(second):
                handler.emit(self.record())
            handler.emit(self.record())
            worker = Thread(target=context.run, args=(handler.emit, self.record()))
            worker.start()
            worker.join(2)
            record = self.record()
            record.pipeworks_remote = True
            handler.emit(record)
        self.assertEqual(len(a), 2)
        self.assertEqual(b, [])
        self.assertIsNone(relay.current_route())

    def test_object_formatting_cannot_recursively_reenter_transport(self):
        route, sent = self.route()

        class Noisy:
            def __repr__(self):
                route.emit(logging.LogRecord("recursive", logging.WARNING, __file__, 0, "nested", (), None))
                return "safe representation"

        record = self.record()
        class Broken:
            def __str__(self):
                raise ValueError("bad str")

            def __repr__(self):
                raise ValueError("bad repr")

        record.extra = Noisy()
        record.mapping = {Broken(): Broken()}
        route.emit(record)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1]["extra"], "safe representation")
        self.assertEqual(sent[0][1]["mapping"], {"<Broken>": "<Broken>"})

    def test_send_failure_stops_route_without_recursive_logging(self):
        stop = Event()
        route = relay.LogRoute(lambda packet: (_ for _ in ()).throw(BrokenPipeError()), stop,
                               {"root": logging.DEBUG, "loggers": {}, "disable": 0}, "p", "id")
        with patch("logging.Logger._log", side_effect=AssertionError("recursive log")):
            route.emit(self.record())
            route.emit(self.record())
        self.assertTrue(stop.is_set())
        self.assertFalse(route.active)

    def test_nested_output_writer_restores_previous_writer_and_route(self):
        import sys
        from pipeworks.main import _ThreadOutput, _use_output_writer

        first, a = self.route()
        second, b = self.route()
        second.execution_id = "run-2"
        first_writer, second_writer = relay.PrintAdapter(first), relay.PrintAdapter(second)
        output = _ThreadOutput(StringIO())
        previous_writes = []
        output.current.write = previous_writes.append
        with patch("sys.stdout", output):
            with _use_output_writer(first_writer):
                print("outer", end="")
                with _use_output_writer(second_writer):
                    print("inner", end="")
                self.assertIs(relay.current_route(), first)
                print(" tail")
            self.assertIsNone(relay.current_route())
            print("original")
        self.assertEqual([data["msg"] for _, data in a], ["outer tail"])
        self.assertEqual([data["msg"] for _, data in b], ["inner"])
        self.assertEqual("".join(previous_writes), "original\n")

    def test_prepared_nonpropagating_loggers_are_relayed_without_duplicate_handlers(self):
        import subprocess
        import sys
        import textwrap

        code = textwrap.dedent('''
            import logging
            from io import StringIO
            from threading import Event
            from pipeworks.remote_logging import LogRoute, install_relay, use_route
            logger = logging.getLogger("prepared.worker")
            logger.setLevel(logging.WARNING)
            logger.disabled = True
            logger.propagate = False
            output = StringIO()
            logger.addHandler(logging.StreamHandler(output))
            policy = {"root": logging.DEBUG, "loggers": {}, "disable": 0}
            install_relay(policy)
            sent = []
            route = LogRoute(sent.append, Event(), policy, "p", "id")
            with use_route(route):
                logger.debug("nonpropagating")
                logging.getLogger("new.worker").info("new logger")
            assert [data["msg"] for _, data in sent] == ["nonpropagating", "new logger"]
            assert output.getvalue() == ""
        ''')
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_print_debug_is_filtered_at_info_and_disable_threshold(self):
        for policy in ({"root": logging.INFO}, {"disable": logging.DEBUG}):
            route, sent = self.route(**policy) if "root" not in policy else self.route(logging.INFO)
            writer = relay.PrintAdapter(route)
            writer("hidden\n")
            writer.close()
            self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
