# Copyright 2017, Google Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above
# copyright notice, this list of conditions and the following disclaimer
# in the documentation and/or other materials provided with the
# distribution.
#     * Neither the name of Google Inc. nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import grpc
import mock
import pytest

from google.gax.future import base


class PollingFutureImpl(base.PollingFuture):
    def _poll_once(self, timeout):  # pragma: NO COVER
        pass

    @property
    def _poll_retry_codes(self):  # pragma: NO COVER
        return []

    def cancel(self):
        return True

    def cancelled(self):
        return False

    def done(self):
        return False

    def running(self):
        return True


def test_polling_future_constructor():
    future = PollingFutureImpl()
    assert not future.done()
    assert not future.cancelled()
    assert future.running()
    assert future.cancel()


def test_set_result():
    future = PollingFutureImpl()
    callback_mock = mock.Mock()

    future.set_result(1)

    assert future.result() == 1
    future.add_done_callback(callback_mock)
    callback_mock.assert_called_once_with(future)


def test_set_exception():
    future = PollingFutureImpl()
    exception = ValueError('meep')

    future.set_exception(exception)

    assert future.exception() == exception
    with pytest.raises(ValueError):
        future.result()

    callback_mock = mock.Mock()
    future.add_done_callback(callback_mock)
    callback_mock.assert_called_once_with(future)


def test_invoke_callback_exception():
    future = PollingFutureImplWithPoll()
    future.set_result(42)

    # This should not raise, despite the callback causing an exception.
    callback_mock = mock.Mock(side_effect=ValueError)
    future.add_done_callback(callback_mock)
    callback_mock.assert_called_once_with(future)


class RetryPoll(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.DEADLINE_EXCEEDED


class PollingFutureImplWithPoll(PollingFutureImpl):
    def __init__(self):
        super(PollingFutureImplWithPoll, self).__init__()
        self.poll_count = 0

    def _poll_once(self, timeout):
        self.poll_count += 1
        if self.poll_count < 3:
            raise RetryPoll()
        self.set_result(42)

    @property
    def _poll_retry_codes(self):
        return [grpc.StatusCode.DEADLINE_EXCEEDED]


@mock.patch('time.sleep')
def test_result_with_polling(unusued_sleep):
    future = PollingFutureImplWithPoll()

    result = future.result()

    assert result == 42
    assert future.poll_count == 3
    # Repeated calls should not cause additional polling
    assert future.result() == result
    assert future.poll_count == 3


@mock.patch('time.sleep')
def test_callback_background_thread(unused_sleep):
    future = PollingFutureImplWithPoll()
    callback_mock = mock.Mock()

    future.add_done_callback(callback_mock)

    assert future._polling_thread is not None

    future._polling_thread.join()

    callback_mock.assert_called_once_with(future)
