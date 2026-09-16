"""Asynchronous start/stop requests; called only from the ROS executor thread."""

from collections import OrderedDict
import json
import time


class RecordingRpc:
    def __init__(self, routes, publish, timeout_s, cache_size):
        # command topic -> (service client, request factory, response topic, bag field)
        self.routes = routes
        self.publish = publish
        self.timeout_s = timeout_s
        self.cache_size = cache_size
        self.completed = OrderedDict()
        self.pending = None

    def _reply(self, topic, request_id, success, error='', bag_name=''):
        payload = dict(requestId=request_id, success=success,
                       error_message=error, bag_name=bag_name)
        self.publish(self.routes[topic][2], payload)
        return payload

    def _remember(self, request_id, topic, payload):
        self.completed[request_id] = (topic, payload)
        while len(self.completed) > self.cache_size:
            self.completed.popitem(last=False)

    def handle(self, topic, payload, retained):
        if topic not in self.routes:
            return
        # Never execute historical commands delivered on subscription/reconnection.
        if retained:
            return
        try:
            data = json.loads(payload)
            request_id = data.get('requestId') if isinstance(data, dict) else None
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError('requestId must be a non-empty string')
        except (ValueError, UnicodeError):
            self._reply(topic, '', False, 'Expected JSON object with non-empty requestId')
            return
        if request_id in self.completed:
            previous_topic, response = self.completed[request_id]
            if previous_topic == topic:
                self.publish(self.routes[topic][2], response)
            else:
                self._reply(topic, request_id, False, 'requestId already used for another command')
            return
        if self.pending is not None:
            previous_topic, previous_id, _, _ = self.pending
            if (topic, request_id) == (previous_topic, previous_id):
                return
            self._reply(topic, request_id, False, 'Another recording request is pending')
            return
        client, request_factory, _, _ = self.routes[topic]
        if not client.service_is_ready():
            response = self._reply(topic, request_id, False, 'Rosbag service unavailable')
            self._remember(request_id, topic, response)
            return
        try:
            future = client.call_async(request_factory())
        except Exception as error:
            response = self._reply(topic, request_id, False, f'Service call failed: {error}')
            self._remember(request_id, topic, response)
            return
        self.pending = (topic, request_id, future, time.monotonic())

    def poll(self):
        if self.pending is None:
            return
        topic, request_id, future, started = self.pending
        client, _, _, bag_field = self.routes[topic]
        if future.done():
            try:
                result = future.result()
                response = self._reply(topic, request_id, bool(result.success),
                                       result.error_message, getattr(result, bag_field))
            except Exception as error:
                response = self._reply(topic, request_id, False, f'Service failed: {error}')
        elif time.monotonic() - started >= self.timeout_s:
            # Removing the local future cannot cancel a service already executing.
            client.remove_pending_request(future)
            future.cancel()
            response = self._reply(topic, request_id, False,
                                   'Service timeout; recording outcome unknown, check recording_state')
        else:
            return
        self._remember(request_id, topic, response)
        self.pending = None
