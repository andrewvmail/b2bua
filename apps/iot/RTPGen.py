# Copyright (c) 2018 Sippy Software, Inc. All rights reserved.
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation and/or
# other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from threading import Thread, Lock

#import sys
#sys.path.append('../..')

from math import floor

from elperiodic.ElPeriodic import ElPeriodic

from rtpsynth.RtpSynth import RtpSynth

from sippy.Core.EventDispatcher import ED2
from sippy.Time.clock_dtime import clock_getdtime, CLOCK_MONOTONIC

RTPGenInit = 0
RTPGenRun = 1
RTPGenSuspend = 2
RTPGenStop = 3

class RTPGen(Thread):
    daemon = True
    ptime = 0.030
    elp = None
    rsth = None
    state_lock = Lock()
    state = RTPGenInit
    userv = None
    target = None
    pl_queue = None
    plq_lock = Lock()

    def __init__(self):
        Thread.__init__(self)
        self.pl_queue = []

    def start(self, userv, target):
        self.state_lock.acquire()
        self.target = target
        self.userv = userv
        if self.state == RTPGenSuspend:
            self.state = RTPGenRun
            self.state_lock.release()
            return
        self.state_lock.release()
        pfreq = 1.0 / self.ptime
        self.elp = ElPeriodic(pfreq)
        self.rsth = RtpSynth(8000, 30)
        Thread.start(self)

    def enqueue(self, pload):
        self.plq_lock.acquire()
        self.pl_queue.append(pload)
        self.plq_lock.release()

    def dequeue(self):
        self.plq_lock.acquire()
        if len(self.pl_queue) > 0:
            rval = self.pl_queue.pop(0)
        else:
            rval = None
        self.plq_lock.release()
        return rval

    def run(self):
        stime = clock_getdtime(CLOCK_MONOTONIC)
        self.state_lock.acquire()
        if self.state == RTPGenStop:
            self.state_lock.release()
            return
        self.state = RTPGenRun
        self.state_lock.release()
        last_npkt = -1
        while True:
            self.state_lock.acquire()
            cstate = self.state
            self.state_lock.release()
            if cstate == RTPGenStop:
                return
            ntime = clock_getdtime(CLOCK_MONOTONIC)
            npkt = floor((ntime - stime) / self.ptime)
            for i in range(0, npkt - last_npkt):
                if cstate == RTPGenSuspend:
                    self.rsth.next_pkt(240, 0)
                else:
                    rp = self.rsth.next_pkt(240, 0, pload = self.dequeue())
                    self.userv.send_to(rp, self.target)
            #print(npkt - last_npkt)
            last_npkt = npkt
            self.elp.procrastinate()

    def stop(self):
        self.state_lock.acquire()
        pstate = self.state
        if self.state in (RTPGenRun, RTPGenSuspend):
            self.state = RTPGenStop
        self.state_lock.release()
        if pstate in (RTPGenRun, RTPGenSuspend):
            self.join()
        self.userv = None
        self.state_lock.acquire()
        self.state = RTPGenInit
        self.state_lock.release()

    def suspend(self):
        self.state_lock.acquire()
        if self.state == RTPGenRun:
            self.state = RTPGenSuspend
        else:
            etext = 'suspend() is called in the wrong state: %s' % self.state
            self.state_lock.release()
            raise Exception(etext)
        self.state_lock.release()

class FakeUserv(object):
    nsent = 0

    def send_to(self, *args):
        self.nsent += 1
        pass

if __name__ == '__main__':
    r = RTPGen()
    s = FakeUserv()
    t = ('127.0.0.1', 12345)
    r.start(s, t)
    from time import sleep
    sleep(2)
    r.suspend()
    sleep(1)
    r.start(s, t)
    sleep(2)
    r.stop()
    try:
        r.suspend()
    except:
        pass
    else:
        raise Exception('suspend() test failed')
    nsent_base = 135
    nsent_div = 2
    if s.nsent < (nsent_base - nsent_div) or s.nsent > (nsent_base + nsent_div):
        raise Exception('nsent test failed')
