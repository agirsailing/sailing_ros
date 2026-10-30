"""Bounded, asynchronous ping requests, processed on the ROS executor."""

from collections import OrderedDict
import json
import time


class MarkRpc:
    def __init__(self, client, request_factory, publish, response_topic,
                 timeout_s, cache_size):
        self.client = client
        self.request_factory = request_factory
        self.publish = publish
        self.response_topic = response_topic
        self.timeout_s = timeout_s
        self.cache_size = cache_size
        self.completed = OrderedDict()
        self.pending = None

    def _reply(self, request_id, success, error='', mark=None):
        payload = {'requestId': request_id, 'success': success,
                   'error_message': error, 'mark': mark}
        self.publish(self.response_topic, payload)
        return payload

    def _remember(self, request_id, kind, response):
        self.completed[request_id] = (kind, response)
        while len(self.completed) > self.cache_size:
            self.completed.popitem(last=False)

    def handle(self, payload, retained=False):
        if retained:
            return
        request_id = ''
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            request_id = data.get('requestId')
            if not isinstance(request_id, str) or not 1 <= len(request_id.strip()) <= 128:
                request_id = ''
                raise ValueError('requestId must contain 1 to 128 characters')
            kind = data.get('type')
            if type(kind) is not int or kind not in (0, 1, 2):
                raise ValueError('type must be 0 (Committee), 1 (Pin) or 2 (Windward)')
            if set(data) != {'requestId', 'type'}:
                raise ValueError('Send only requestId and type; ROS captures the GPS position')
        except (ValueError, UnicodeError) as error:
            self._reply(request_id, False, str(error))
            return
        if request_id in self.completed:
            previous_kind, response = self.completed[request_id]
            if kind == previous_kind:
                self.publish(self.response_topic, response)
            else:
                self._reply(request_id, False, 'requestId already used for another mark type')
            return
        if self.pending is not None:
            previous_id, previous_kind, _, _ = self.pending
            if (request_id, kind) == (previous_id, previous_kind):
                return
            response = self._reply(request_id, False, 'Another ping request is pending')
            if request_id != previous_id:
                # A rejected concurrent request must stay rejected on QoS redelivery.
                self._remember(request_id, kind, response)
            return
        if not self.client.service_is_ready():
            response = self._reply(request_id, False, 'Mark service unavailable')
            self._remember(request_id, kind, response)
            return
        request = self.request_factory()
        request.type = kind
        try:
            future = self.client.call_async(request)
        except Exception as error:
            response = self._reply(request_id, False, f'Service call failed: {error}')
            self._remember(request_id, kind, response)
            return
        self.pending = (request_id, kind, future, time.monotonic())

    def poll(self):
        if self.pending is None:
            return
        request_id, kind, future, started = self.pending
        if future.done():
            try:
                result = future.result()
                mark = None
                if result.success:
                    item = result.mark
                    mark = {
                        'type': item.type, 'lat': item.lat, 'lon': item.lon,
                        'header': {
                            'frame_id': item.header.frame_id,
                            'stamp': {'sec': item.header.stamp.sec,
                                      'nanosec': item.header.stamp.nanosec},
                        },
                    }
                response = self._reply(request_id, bool(result.success),
                                       result.error_message, mark)
            except Exception as error:
                response = self._reply(request_id, False, f'Service failed: {error}')
        elif time.monotonic() - started >= self.timeout_s:
            self.client.remove_pending_request(future)
            future.cancel()
            response = self._reply(request_id, False,
                                   'Service timeout; ping outcome unknown, check the map')
        else:
            return
        self._remember(request_id, kind, response)
        self.pending = None
