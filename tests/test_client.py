# coding: utf-8
import os
import json
import pytest
import subprocess
import sys
import time

from textwrap import dedent
from sentry_sdk import (
    Hub,
    Client,
    add_breadcrumb,
    configure_scope,
    capture_message,
    capture_exception,
    capture_event,
    start_transaction,
    set_tag,
)
from sentry_sdk.integrations.executing import ExecutingIntegration
from sentry_sdk.transport import Transport
from sentry_sdk._compat import reraise, text_type, PY2
from sentry_sdk.utils import HAS_CHAINED_EXCEPTIONS
from sentry_sdk.serializer import MAX_DATABAG_BREADTH
from sentry_sdk.consts import DEFAULT_MAX_BREADCRUMBS

if PY2:
    # Importing ABCs from collections is deprecated, and will stop working in 3.8
    # https://github.com/python/cpython/blob/master/Lib/collections/__init__.py#L49
    from collections import Mapping
else:
    # New in 3.3
    # https://docs.python.org/3/library/collections.abc.html
    from collections.abc import Mapping


class EventCaptured(Exception):
    pass


class _TestTransport(Transport):
    def capture_event(self, event):
        raise EventCaptured(event)


def test_transport_option(monkeypatch):
    if "SENTRY_DSN" in os.environ:
        monkeypatch.delenv("SENTRY_DSN")

    dsn = "https://foo@sentry.io/123"
    dsn2 = "https://bar@sentry.io/124"
    assert str(Client(dsn=dsn).dsn) == dsn
    assert Client().dsn is None

    monkeypatch.setenv("SENTRY_DSN", dsn)
    transport = Transport({"dsn": dsn2})
    assert text_type(transport.parsed_dsn) == dsn2
    assert str(Client(transport=transport).dsn) == dsn


@pytest.mark.parametrize(
    "testcase",
    [
        {
            "dsn": "http://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": None,
            "arg_http_proxy": "http://localhost/123",
            "arg_https_proxy": None,
            "expected_proxy_scheme": "http",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": None,
            "arg_http_proxy": "https://localhost/123",
            "arg_https_proxy": None,
            "expected_proxy_scheme": "https",
        },
        {
            "dsn": "http://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": None,
            "arg_http_proxy": "http://localhost/123",
            "arg_https_proxy": "https://localhost/123",
            "expected_proxy_scheme": "http",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": None,
            "arg_http_proxy": "http://localhost/123",
            "arg_https_proxy": "https://localhost/123",
            "expected_proxy_scheme": "https",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": None,
            "arg_http_proxy": "http://localhost/123",
            "arg_https_proxy": None,
            "expected_proxy_scheme": "http",
        },
        {
            "dsn": "http://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": None,
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": None,
        },
        {
            "dsn": "http://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": None,
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": "http",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": "https://localhost/123",
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": "https",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": None,
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": "http",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": "https://localhost/123",
            "arg_http_proxy": "",
            "arg_https_proxy": "",
            "expected_proxy_scheme": None,
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": "https://localhost/123",
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": "https",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": None,
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": "http",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": "https://localhost/123",
            "arg_http_proxy": None,
            "arg_https_proxy": "",
            "expected_proxy_scheme": "http",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": "https://localhost/123",
            "arg_http_proxy": "",
            "arg_https_proxy": None,
            "expected_proxy_scheme": "https",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": "https://localhost/123",
            "arg_http_proxy": None,
            "arg_https_proxy": "",
            "expected_proxy_scheme": None,
        },
        {
            "dsn": "http://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": "https://localhost/123",
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": "http",
        },
        # NO_PROXY testcases
        {
            "dsn": "http://foo@sentry.io/123",
            "env_http_proxy": "http://localhost/123",
            "env_https_proxy": None,
            "env_no_proxy": "sentry.io,example.com",
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": None,
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": "https://localhost/123",
            "env_no_proxy": "example.com,sentry.io",
            "arg_http_proxy": None,
            "arg_https_proxy": None,
            "expected_proxy_scheme": None,
        },
        {
            "dsn": "http://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": None,
            "env_no_proxy": "sentry.io,example.com",
            "arg_http_proxy": "http://localhost/123",
            "arg_https_proxy": None,
            "expected_proxy_scheme": "http",
        },
        {
            "dsn": "https://foo@sentry.io/123",
            "env_http_proxy": None,
            "env_https_proxy": None,
            "env_no_proxy": "sentry.io,example.com",
            "arg_http_proxy": None,
            "arg_https_proxy": "https://localhost/123",
            "expected_proxy_scheme": "https",
        },
    ],
)
def test_proxy(monkeypatch, testcase):
    if testcase["env_http_proxy"] is not None:
        monkeypatch.setenv("HTTP_PROXY", testcase["env_http_proxy"])
    if testcase["env_https_proxy"] is not None:
        monkeypatch.setenv("HTTPS_PROXY", testcase["env_https_proxy"])
    if testcase.get("env_no_proxy") is not None:
        monkeypatch.setenv("NO_PROXY", testcase["env_no_proxy"])
    kwargs = {}
    if testcase["arg_http_proxy"] is not None:
        kwargs["http_proxy"] = testcase["arg_http_proxy"]
    if testcase["arg_https_proxy"] is not None:
        kwargs["https_proxy"] = testcase["arg_https_proxy"]
    client = Client(testcase["dsn"], **kwargs)
    if testcase["expected_proxy_scheme"] is None:
        assert client.transport._pool.proxy is None
    else:
        assert client.transport._pool.proxy.scheme == testcase["expected_proxy_scheme"]


def test_simple_transport(sentry_init):
    events = []
    sentry_init(transport=events.append)
    capture_message("Hello World!")
    assert events[0]["message"] == "Hello World!"


def test_ignore_errors(sentry_init, capture_events):
    class MyDivisionError(ZeroDivisionError):
        pass

    def raise_it(exc_info):
        reraise(*exc_info)

    sentry_init(ignore_errors=[ZeroDivisionError], transport=_TestTransport())
    Hub.current._capture_internal_exception = raise_it

    def e(exc):
        try:
            raise exc
        except Exception:
            capture_exception()

    e(ZeroDivisionError())
    e(MyDivisionError())
    pytest.raises(EventCaptured, lambda: e(ValueError()))


def test_with_locals_enabled(sentry_init, capture_events):
    sentry_init(with_locals=True)
    events = capture_events()
    try:
        1 / 0
    except Exception:
        capture_exception()

    (event,) = events

    assert all(
        frame["vars"]
        for frame in event["exception"]["values"][0]["stacktrace"]["frames"]
    )


def test_with_locals_disabled(sentry_init, capture_events):
    sentry_init(with_locals=False)
    events = capture_events()
    try:
        1 / 0
    except Exception:
        capture_exception()

    (event,) = events

    assert all(
        "vars" not in frame
        for frame in event["exception"]["values"][0]["stacktrace"]["frames"]
    )


@pytest.mark.parametrize("integrations", [[], [ExecutingIntegration()]])
def test_function_names(sentry_init, capture_events, integrations):
    sentry_init(integrations=integrations)
    events = capture_events()

    def foo():
        try:
            bar()
        except Exception:
            capture_exception()

    def bar():
        1 / 0

    foo()

    (event,) = events
    (thread,) = event["exception"]["values"]
    functions = [x["function"] for x in thread["stacktrace"]["frames"]]

    if integrations:
        assert functions == [
            "test_function_names.<locals>.foo",
            "test_function_names.<locals>.bar",
        ]
    else:
        assert functions == ["foo", "bar"]


def test_attach_stacktrace_enabled(sentry_init, capture_events):
    sentry_init(attach_stacktrace=True)
    events = capture_events()

    def foo():
        bar()

    def bar():
        capture_message("HI")

    foo()

    (event,) = events
    (thread,) = event["threads"]["values"]
    functions = [x["function"] for x in thread["stacktrace"]["frames"]]

    assert functions[-2:] == ["foo", "bar"]


def test_attach_stacktrace_enabled_no_locals(sentry_init, capture_events):
    sentry_init(attach_stacktrace=True, with_locals=False)
    events = capture_events()

    def foo():
        bar()

    def bar():
        capture_message("HI")

    foo()

    (event,) = events
    (thread,) = event["threads"]["values"]
    local_vars = [x.get("vars") for x in thread["stacktrace"]["frames"]]
    assert local_vars[-2:] == [None, None]


def test_attach_stacktrace_in_app(sentry_init, capture_events):
    sentry_init(attach_stacktrace=True, in_app_exclude=["_pytest"])
    events = capture_events()

    capture_message("hi")

    (event,) = events
    (thread,) = event["threads"]["values"]
    frames = thread["stacktrace"]["frames"]
    pytest_frames = [f for f in frames if f["module"].startswith("_pytest")]
    assert pytest_frames
    assert all(f["in_app"] is False for f in pytest_frames)
    assert any(f["in_app"] for f in frames)


def test_attach_stacktrace_disabled(sentry_init, capture_events):
    sentry_init(attach_stacktrace=False)
    events = capture_events()
    capture_message("HI")

    (event,) = events
    assert "threads" not in event


def test_capture_event_works(sentry_init):
    sentry_init(transport=_TestTransport())
    pytest.raises(EventCaptured, lambda: capture_event({}))
    pytest.raises(EventCaptured, lambda: capture_event({}))


@pytest.mark.parametrize("num_messages", [10, 20])
def test_atexit(tmpdir, monkeypatch, num_messages):
    app = tmpdir.join("app.py")
    app.write(
        dedent(
            """
    import time
    from sentry_sdk import init, transport, capture_message

    def send_event(self, event):
        time.sleep(0.1)
        print(event["message"])

    transport.HttpTransport._send_event = send_event
    init("http://foobar@localhost/123", shutdown_timeout={num_messages})

    for _ in range({num_messages}):
        capture_message("HI")
    """.format(
                num_messages=num_messages
            )
        )
    )

    start = time.time()
    output = subprocess.check_output([sys.executable, str(app)])
    end = time.time()

    # Each message takes at least 0.1 seconds to process
    assert int(end - start) >= num_messages / 10

    assert output.count(b"HI") == num_messages


def test_configure_scope_available(sentry_init, request, monkeypatch):
    # Test that scope is configured if client is configured
    sentry_init()

    with configure_scope() as scope:
        assert scope is Hub.current.scope
        scope.set_tag("foo", "bar")

    calls = []

    def callback(scope):
        calls.append(scope)
        scope.set_tag("foo", "bar")

    assert configure_scope(callback) is None
    assert len(calls) == 1
    assert calls[0] is Hub.current.scope


@pytest.mark.tests_internal_exceptions
def test_client_debug_option_enabled(sentry_init, caplog):
    sentry_init(debug=True)

    Hub.current._capture_internal_exception((ValueError, ValueError("OK"), None))
    assert "OK" in caplog.text


@pytest.mark.tests_internal_exceptions
@pytest.mark.parametrize("with_client", (True, False))
def test_client_debug_option_disabled(with_client, sentry_init, caplog):
    if with_client:
        sentry_init()

    Hub.current._capture_internal_exception((ValueError, ValueError("OK"), None))
    assert "OK" not in caplog.text


def test_scope_initialized_before_client(sentry_init, capture_events):
    """
    This is a consequence of how configure_scope() works. We must
    make `configure_scope()` a noop if no client is configured. Even
    if the user later configures a client: We don't know that.
    """
    with configure_scope() as scope:
        scope.set_tag("foo", 42)

    sentry_init()

    events = capture_events()
    capture_message("hi")
    (event,) = events

    assert "tags" not in event


def test_weird_chars(sentry_init, capture_events):
    sentry_init()
    events = capture_events()
    # fmt: off
    capture_message(u"föö".encode("latin1"))
    # fmt: on
    (event,) = events
    assert json.loads(json.dumps(event)) == event


def test_nan(sentry_init, capture_events):
    sentry_init()
    events = capture_events()

    try:
        # should_repr_strings=False
        set_tag("mynan", float("nan"))

        # should_repr_strings=True
        nan = float("nan")  # noqa
        1 / 0
    except Exception:
        capture_exception()

    (event,) = events
    frames = event["exception"]["values"][0]["stacktrace"]["frames"]
    (frame,) = frames
    assert frame["vars"]["nan"] == "nan"
    assert event["tags"]["mynan"] == "nan"


def test_cyclic_frame_vars(sentry_init, capture_events):
    sentry_init()
    events = capture_events()

    try:
        a = {}
        a["a"] = a
        1 / 0
    except Exception:
        capture_exception()

    (event,) = events
    assert event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["a"] == {
        "a": "<cyclic>"
    }


def test_cyclic_data(sentry_init, capture_events):
    sentry_init()
    events = capture_events()

    with configure_scope() as scope:
        data = {}
        data["is_cyclic"] = data

        other_data = ""
        data["not_cyclic"] = other_data
        data["not_cyclic2"] = other_data
        scope.set_extra("foo", data)

    capture_message("hi")
    (event,) = events

    data = event["extra"]["foo"]
    assert data == {"not_cyclic2": "", "not_cyclic": "", "is_cyclic": "<cyclic>"}


def test_databag_depth_stripping(sentry_init, capture_events, benchmark):
    sentry_init()
    events = capture_events()

    value = ["a"]
    for _ in range(100000):
        value = [value]

    @benchmark
    def inner():
        del events[:]
        try:
            a = value  # noqa
            1 / 0
        except Exception:
            capture_exception()

        (event,) = events

        assert len(json.dumps(event)) < 10000


def test_databag_string_stripping(sentry_init, capture_events, benchmark):
    sentry_init()
    events = capture_events()

    @benchmark
    def inner():
        del events[:]
        try:
            a = "A" * 1000000  # noqa
            1 / 0
        except Exception:
            capture_exception()

        (event,) = events

        assert len(json.dumps(event)) < 10000


def test_databag_breadth_stripping(sentry_init, capture_events, benchmark):
    sentry_init()
    events = capture_events()

    @benchmark
    def inner():
        del events[:]
        try:
            a = ["a"] * 1000000  # noqa
            1 / 0
        except Exception:
            capture_exception()

        (event,) = events

        assert (
            len(event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["a"])
            == MAX_DATABAG_BREADTH
        )
        assert len(json.dumps(event)) < 10000


@pytest.mark.skipif(not HAS_CHAINED_EXCEPTIONS, reason="Only works on 3.3+")
def test_chained_exceptions(sentry_init, capture_events):
    sentry_init()
    events = capture_events()

    try:
        try:
            raise ValueError()
        except Exception:
            1 / 0
    except Exception:
        capture_exception()

    (event,) = events

    e1, e2 = event["exception"]["values"]

    # This is the order all other SDKs send chained exceptions in. Including
    # Raven-Python.

    assert e1["type"] == "ValueError"
    assert e2["type"] == "ZeroDivisionError"


@pytest.mark.tests_internal_exceptions
def test_broken_mapping(sentry_init, capture_events):
    sentry_init()
    events = capture_events()

    class C(Mapping):
        def broken(self, *args, **kwargs):
            raise Exception("broken")

        __getitem__ = broken
        __setitem__ = broken
        __delitem__ = broken
        __iter__ = broken
        __len__ = broken

        def __repr__(self):
            return "broken"

    try:
        a = C()  # noqa
        1 / 0
    except Exception:
        capture_exception()

    (event,) = events
    assert (
        event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["a"]
        == "<failed to serialize, use init(debug=True) to see error logs>"
    )


def test_mapping_sends_exception(sentry_init, capture_events):
    sentry_init()
    events = capture_events()

    class C(Mapping):
        def __iter__(self):
            try:
                1 / 0
            except ZeroDivisionError:
                capture_exception()
            yield "hi"

        def __len__(self):
            """List length"""
            return 1

        def __getitem__(self, ii):
            """Get a list item"""
            if ii == "hi":
                return "hi"

            raise KeyError()

    try:
        a = C()  # noqa
        1 / 0
    except Exception:
        capture_exception()

    (event,) = events

    assert event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["a"] == {
        "hi": "'hi'"
    }


def test_object_sends_exception(sentry_init, capture_events):
    sentry_init()
    events = capture_events()

    class C(object):
        def __repr__(self):
            try:
                1 / 0
            except ZeroDivisionError:
                capture_exception()
            return "hi, i am a repr"

    try:
        a = C()  # noqa
        1 / 0
    except Exception:
        capture_exception()

    (event,) = events

    assert (
        event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["a"]
        == "hi, i am a repr"
    )


def test_errno_errors(sentry_init, capture_events):
    sentry_init()
    events = capture_events()

    class Foo(Exception):
        errno = 69

    capture_exception(Foo())

    (event,) = events

    (exception,) = event["exception"]["values"]
    assert exception["mechanism"]["meta"]["errno"]["number"] == 69


def test_non_string_variables(sentry_init, capture_events):
    """There is some extremely terrible code in the wild that
    inserts non-strings as variable names into `locals()`."""

    sentry_init()
    events = capture_events()

    try:
        locals()[42] = True
        1 / 0
    except ZeroDivisionError:
        capture_exception()

    (event,) = events

    (exception,) = event["exception"]["values"]
    assert exception["type"] == "ZeroDivisionError"
    (frame,) = exception["stacktrace"]["frames"]
    assert frame["vars"]["42"] == "True"


def test_dict_changed_during_iteration(sentry_init, capture_events):
    """
    Some versions of Bottle modify the WSGI environment inside of this __repr__
    impl: https://github.com/bottlepy/bottle/blob/0.12.16/bottle.py#L1386

    See https://github.com/getsentry/sentry-python/pull/298 for discussion
    """
    sentry_init(send_default_pii=True)
    events = capture_events()

    class TooSmartClass(object):
        def __init__(self, environ):
            self.environ = environ

        def __repr__(self):
            if "my_representation" in self.environ:
                return self.environ["my_representation"]

            self.environ["my_representation"] = "<This is me>"
            return self.environ["my_representation"]

    try:
        environ = {}
        environ["a"] = TooSmartClass(environ)
        1 / 0
    except ZeroDivisionError:
        capture_exception()

    (event,) = events
    (exception,) = event["exception"]["values"]
    (frame,) = exception["stacktrace"]["frames"]
    assert frame["vars"]["environ"] == {"a": "<This is me>"}


@pytest.mark.parametrize(
    "dsn",
    [
        "http://894b7d594095440f8dfea9b300e6f572@localhost:8000/2",
        "http://894b7d594095440f8dfea9b300e6f572@localhost:8000/2",
    ],
)
def test_init_string_types(dsn, sentry_init):
    # Allow unicode strings on Python 3 and both on Python 2 (due to
    # unicode_literals)
    #
    # Supporting bytes on Python 3 is not really wrong but probably would be
    # extra code
    sentry_init(dsn)
    assert (
        Hub.current.client.dsn
        == "http://894b7d594095440f8dfea9b300e6f572@localhost:8000/2"
    )


def test_envelope_types():
    """
    Tests for calling the right transport method (capture_event vs
    capture_envelope) from the SDK client for different data types.
    """

    envelopes = []
    events = []

    class CustomTransport(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)

        def capture_event(self, event):
            events.append(event)

    with Hub(Client(traces_sample_rate=1.0, transport=CustomTransport())):
        event_id = capture_message("hello")

        # Assert error events get passed in via capture_event
        assert not envelopes
        event = events.pop()

        assert event["event_id"] == event_id
        assert "type" not in event

        with start_transaction(name="foo"):
            pass

        # Assert transactions get passed in via capture_envelope
        assert not events
        envelope = envelopes.pop()

        (item,) = envelope.items
        assert item.data_category == "transaction"
        assert item.headers.get("type") == "transaction"

    assert not envelopes
    assert not events


@pytest.mark.parametrize(
    "sdk_options, expected_breadcrumbs",
    [({}, DEFAULT_MAX_BREADCRUMBS), ({"max_breadcrumbs": 50}, 50)],
)
def test_max_breadcrumbs_option(
    sentry_init, capture_events, sdk_options, expected_breadcrumbs
):
    sentry_init(sdk_options)
    events = capture_events()

    for _ in range(1231):
        add_breadcrumb({"type": "sourdough"})

    capture_message("dogs are great")

    assert len(events[0]["breadcrumbs"]["values"]) == expected_breadcrumbs


def test_multiple_positional_args(sentry_init):
    with pytest.raises(TypeError) as exinfo:
        sentry_init(1, None)
    assert "Only single positional argument is expected" in str(exinfo.value)
