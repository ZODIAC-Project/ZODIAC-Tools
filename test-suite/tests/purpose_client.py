import logging
import time
import datetime

import logging
logging.disable(logging.CRITICAL)

class PurposeClient:
    """
    A Purpose-Aware MQTT Client that uses a Paho Client under the Hood.
    It sends, subscribes and reserves channels for given purposes and allows
    to keep track of which messages should or should not be received to
    test the robustness of a PBAC system.
    """

    PurposeSet = list

    RESERVE = "!RESERVE"
    AP = "!AP"
    AIP = "!AIP"
    SETTING = "!PBAC"
    PRESUB = "!PBAC/PRESUB"

    def __init__(self, client, log_problems=True, purpose_aware=False, qos=0, presub=False) -> None:
        self.client = client
        # self.client.on_message = lambda x, y, msg: print(msg.payload.decode("utf-8"))
        self.logger = logging.getLogger(__name__)
        self.reset_stats()
        self.client.on_connect = self.on_connect
        if log_problems:
            self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.purpose_aware = purpose_aware
        self.presub = presub
        self.qos = qos
        self.verbosity = 2
        self.problems = 0

        self.start_time = 0.0
        self.timeout = 10.0

        # assign methods, not sure if smart
        self.loop_start = self.client.loop_start
        self.loop_stop = self.client.loop_stop
        self.loop_forever = self.client.loop_forever
        self.message_callback_add = self.client.message_callback_add

        self.subscriptions_pending = []

        def on_subscribe_manage_pending(client, userdata, mid, granted_qos, properties=None):
            self.logger.debug("ack for subscription {}".format(mid))
            try:
                self.subscriptions_pending.remove(mid)
            except ValueError:
                # mid not in pending list; ignore
                pass

        client.on_subscribe = on_subscribe_manage_pending


    def _ensure_connected(self, timeout=5.0):
        """Wait briefly for reconnect if the client is currently disconnected."""
        if self.client.is_connected():
            return
        self.logger.warning("Client not connected, attempting reconnect...")
        if hasattr(self, "connection_data"):
            a, kw = self.connection_data
            try:
                self.client.connect(*a, **kw)
            except Exception as exc:
                self.logger.warning("Reconnect attempt failed: %s", exc)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.client.is_connected():
                return
            time.sleep(0.1)
        raise RuntimeError(f"MQTT client not connected after waiting {timeout}s")

    def wait_for_subscriptions(self):
        TIMEOUT = 30
        TICK = 0.01
        timeout = TIMEOUT

        self.logger.debug("waiting for subscriptions...")

        while timeout > 0 and len(self.subscriptions_pending) > 0:
            time.sleep(TICK)
            timeout -= TICK

        if timeout <= 0:
            self.logger.warning("subscription wait timer timed out!")

        return


    def connect(self, *args, **kwargs):
        self.connection_data = (args, kwargs)
        logging.debug("saving connection data: {}".format(self.connection_data))
        return self.client.connect(*args, **kwargs)
        # self.loop_start()



    def reset_stats(self):
        self.cases = 0
        self.problems = 0
        self.expected_to_receive = []
        self.expected_to_not_receive = []
        self.unwanted_messages = []

    def show_stats(self):
        self.problems = 0

        # self.logger.warning("test")

        for msg in self.expected_to_receive:
            self.problems += 1
            print(msg)
            self.logger.warning("  did not receive %s" % msg)

        for msg in self.unwanted_messages:
            self.problems += 1
            print(msg)
            self.logger.warning("  did receive unwanted message %s" % msg)

        print("%i problems for %i cases" % (self.problems, self.cases))
        problems_this_run = self.problems
        self.reset_stats()
        return problems_this_run

    def set_purpose_setting(self, setting: str, value: bool):
        value_string = "true" if value else "false"
        # self.send("PSYS/settings/%s/set" % setting, value_string)
        self.send(self.SETTING + "/SET/%s" % setting, value_string, qos=1)

    def command(self, command: str):
        mi = self.send(self.SETTING + "/" + command, b"")
        mi.wait_for_publish()

    def clear(self):
        self.command("CLEAR")
        time.sleep(1.0)

    def persist(self):
        self.command("PERSIST")

    def load(self):
        self.command("RELOAD")

    def send(self, topic, message, qos=None, retain=False, max_retries=3, retry_delay=1.0):
        self._ensure_connected()
        if not qos:
            qos = self.qos

        payload_size = len(message if isinstance(message, bytes) else str(message).encode("utf-8"))

        last_exc = None
        for attempt in range(max_retries):
            self._ensure_connected()
            result = self.client.publish(topic, payload=message, qos=qos, retain=retain)
            try:
                result.wait_for_publish(timeout=10.0)
                break
            except RuntimeError as exc:
                last_exc = exc
                self.logger.warning(
                    "Publish attempt %d/%d failed: %s — retrying...",
                    attempt + 1, max_retries, exc,
                )
                time.sleep(retry_delay)
        else:
            raise last_exc

        if isinstance(result, tuple):
            _, mid = result
        else:
            mid = getattr(result, "mid", None)
        return result

    def subscribe(self, topic, qos=1):
        # self.logger.debug("subscribing to topic %s" % topic)
        self._ensure_connected()
        result, mid = self.client.subscribe(topic, qos=qos)
        self.logger.debug("subscribed with mid {}, result: {}".format(mid, result))
        if qos > 0:
            self.subscriptions_pending.append(mid)
        return result, mid


    @staticmethod
    def escape_topic(topic):
        return topic.replace("#", "HASH").replace("+", "PLUS")

    def subscribe_with_purpose(self, topic: str, ap: str, qos=0, presub=False):
        topic = self.escape_topic(topic)
        if self.presub or presub:
            cid = self.client._client_id.decode("utf-8")
            mi = self.client.publish(self.PRESUB + "/%s/%s{%s}" % (cid, topic, ap), "", qos=1)
            mi.wait_for_publish()
            return self.subscribe(topic, qos=qos)
        else:
            purpose_topic = (self.AP + "/%s{%s}" % (topic, ap))
            return self.subscribe(purpose_topic, qos=qos)

    def unsubscribe(self, topic: str):
        return self.client.unsubscribe(topic)

    def reserve(self, topic, aip: list = [], pip: list = [], dontwait=False):
        # self.logger.debug(aip)
        self._ensure_connected()
        topic = self.escape_topic(topic)
        purpose_topic = (self.RESERVE + "/%s{%s|%s}" % (topic, ",".join(aip), ",".join(pip)))
        # self.logger.debug(purpose_topic)
        # logging.debug("reserving... %s" % purpose_topic)
        message_info = self.client.publish(purpose_topic, payload=b"", qos=1, retain=False)
        if not dontwait:
            message_info.wait_for_publish()
        return message_info.mid

    def reset_broker(self):
        self.send(self.SETTING + "/RESET", "", qos=1)

    def reset_connection(self):
        self.client.disconnect()
        self.loop_stop()
        time.sleep(2)
        (a, kw) = self.connection_data
        self.client.connect(*a, **kw)
        self.loop_start()
        self._ensure_connected(timeout=10)

    @staticmethod
    def pack_purpose_topic(topic: str, purposes) -> str:
        if purposes:
            return PurposeClient.AIP + "/%s{%s}" % (topic, ",".join(purposes))
        else:
            return topic

    def send_and_expect(self, topic, message, purposes=[]):
        self.expected_to_receive.append(message)
        self.cases += 1
        return self.send(self.pack_purpose_topic(topic, purposes), message)

    def send_and_reject(self, topic, message, purposes: PurposeSet = []):
        self.expected_to_not_receive.append(message)
        self.cases += 1
        return self.send(self.pack_purpose_topic(topic, purposes), message)

    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc, properties=None):
        """
        MQTT on_connect callback. Accepts both legacy and MQTTv5 signatures:
        - (client, userdata, flags, rc)
        - (client, userdata, flags, rc, properties)
        """
        try:
            self.logger.debug("Connected with result code %s properties=%s", rc, getattr(properties, "__dict__", properties))
        except Exception:
            self.logger.debug("Connected with result code %s", rc)
        # reserve("test/ok", ["research", "internal"])
        # reserve("test/no", ["internal"])

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        message = msg.payload
        topic = msg.topic
        if message in self.expected_to_receive:
            self.logger.debug("received expected message %s" % message)
            self.expected_to_receive.remove(message)
        elif message in self.expected_to_not_receive:
            self.logger.warning("received rejected message %s" % message)
            self.unwanted_messages.append(message)
        else:
            self.logger.warning("received unexpected message %s in %s" % (message, topic))

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        """
        MQTT on_disconnect callback. Accepts both legacy and MQTTv5 signatures:
        - (client, userdata, rc)
        - (client, userdata, disconnect_flags, reason_code, properties)
        """
        try:
            self.logger.critical(
                "disconnect! flags=%s reason_code=%s properties=%s",
                disconnect_flags,
                reason_code,
                getattr(properties, "__dict__", properties),
            )
        except Exception:
            self.logger.critical("disconnect! (failed to format properties)")

    def start_timer(self):
        self.starttime = time.perf_counter()

    def stop_timer(self):
        runtime = time.perf_counter() - self.starttime
        self.logger.debug("   timer completed in %fs" % runtime)
        return runtime

    def mass_sub(self, bench_session: str, wait, num):
        self.start_timer()
        subscribed_count = 0
        for i in range(1, num):
            topic = "bench/sub/%s/%i" % (bench_session, i)
            self.logger.debug("subscribing to %s" % topic)
            if self.purpose_aware:
                self.client.subscribe_with_purpose(topic, "bench")
            else:
                self.client.subscribe(topic)
            subscribed_count += 1
            time.sleep(wait)
        runtime = self.stop_timer()
        tp = (subscribed_count / runtime) if runtime > 0 else 0
        return 0, tp

    def bench_with_wait(self, bench_session: str, wait=0.1, num=1000):
        benchname = "bench/%s/%i_%i_%f" % (bench_session, (20), num, wait)
        print("%i @%f" % (num, wait), end=" ")

        if self.purpose_aware:
            self.reserve(benchname, ["benchmarking"])
            time.sleep(0.1)
            self.subscribe_with_purpose(benchname, "benchmarking")
        else:
            self.subscribe(benchname)

        time.sleep(1)
        # print("starting bench... with %f" % wait)

        mids = []

        def on_publish(client, userdata, mid):
            # print(client, userdata, mid)
            # print("received: {}".format(mid))
            if mid not in mids:
                print("not found: {}".format(mid))
            mids.remove(mid)

        self.client.on_publish = on_publish

        self.reset_stats()
        self.start_timer()
        for i in range(num):
            (result, mid) = self.send_and_expect(benchname, ("bench%i" % i).encode("utf-8"))
            # print("sent: {}".format(mid))

            mids.append(mid)
            time.sleep(wait)

        # wait for all messages to arrive
        # print("waiting for queue to clear...")
        timeout = self.timeout
        tick = 0.001
        # while len(self.expected_to_receive) > 0 and timeout > 0:
        while len(mids) > 0 and timeout > 0:
            time.sleep(tick)
            timeout -= tick
            print(len(mids))

        runtime = self.stop_timer()
        tp = num / runtime

        # time.sleep(1)
        problems = self.show_stats()
        if problems > 0:
            tp = 0
        print(" -> %f msg/s, %i problems" % (tp, problems))
        # print("    %i problems" % problems)
        # print("waiting for queue to clear... (%f s)" % queue_clear_time)

        return problems, tp

    def bisect_throughput(self, steps=20, step_time=0.2, num_messages=1000, mode="pub"):

        self.reset_stats()
        fastest_working = step_time
        fastest_broken = 0

        bench_session = datetime.datetime.now().strftime("%H%M%S")

        max_tp = 0
        max_tp_step_time = 0

        while steps:
            steps -= 1
            # print("\n %i steps to go" % steps)
            current_step_time = step_time

            tp = 0  # ensure tp is always defined
            if mode == 'pub':
                self.problems, tp = self.bench_with_wait(bench_session, step_time, num_messages)
            elif mode == 'sub':
                self.problems, tp = self.mass_sub(bench_session, step_time, num_messages)
            else:
                # unsupported mode — treat as no problems and zero throughput
                self.problems = 0
                tp = 0

            if self.problems == 0 and tp > max_tp:
                max_tp = tp
                max_tp_step_time = step_time
                step_time += ((fastest_broken - step_time) / 2)
                self.logger.debug("new fastest time: %fs", fastest_working)
                fastest_working = current_step_time
            else:
                fastest_broken = step_time
                self.logger.debug("new fastest broken: %fs", fastest_broken)
                step_time += ((fastest_working - step_time) / 2)

        self.logger.debug("bisection done sent")
        print("max tp %f with step time %f" % (max_tp, max_tp_step_time))
