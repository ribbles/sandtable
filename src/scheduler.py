#!/usr/bin/python3 -u
import sched
import time
import logging
import json
import socket
import socketserver
from tcpserver import *
from threading import Thread
from collections import deque
import random

from Sand import *
from ledstuff import *
from dialog import *
from Chains import *
from history import *
import board
import digitalio
import mach

# Parameters
POLLING_DELAY   = 0.100     # 1/10 second
DRAW_TIME_MIN   = 18        # 18 Seconds
DRAW_TIME_MAX   = 25*60     # 25 minutes
PROX_SWITCH_SECS= 8         # Number of seconds to wait for taps

PROX_PIN = board.D18
PROX_PIN.direction = digitalio.Direction.INPUT

# Advanced job scheduler setup
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from pytz import utc

jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///%sjobs.sqlite' % DATA_PATH)
}
executors = {
    'default': ThreadPoolExecutor(20),
    'processpool': ProcessPoolExecutor(5)
}
job_defaults = {
    'coalesce': True,
    'max_instances': 3
}

#
# Job actions:
#   "demo"   Run a single demo
#   "method" Draw a specific method
#   "saved"  Draw a saved drawing
#
# Job frequency:
#   "yearly" Run at a specific time and date of the year
#       Data is Hour, Minute, Month, Day
#   "daily" Run at a specific time of the day
#       Data is Hour, Minute
#   "frequency" Run at a specific frequency recurring forever
#       Data is Type (DayOfWeek,Month,Day,Year), Value, Hour, Minute

def JobDemo():
    demo.demoOnce()

class Demo(Thread):
    DIE, QUIET, HALT, RUNNING = -1, 0, 1, 2

    def __init__(self,pause=30):
        super(Demo, self).__init__()
        self._state = self.QUIET
        self._count = 0
        self._pause = pause

    def run(self):
        logging.info( "Demo active" )
        while self._state != self.DIE:
            if self._state == self.QUIET:
                time.sleep( POLLING_DELAY )

            elif self._state == self.RUNNING:        
                self._lightsRandom()
                while self._state == self.RUNNING and self._count != 0:
                    self._count -= 1
                    self._drawRandom()
                    self._drawWait()
                    end = time.time() + self._pause
                    while self._state == self.RUNNING and time.time() < end:
                        time.sleep( POLLING_DELAY )                    
                self._lightsOff()
                if self._state == self.RUNNING:
                    self._state = self.QUIET

            if self._state == self.HALT:
                self._lightsOff()
                self._drawHalt()
                self._state = self.QUIET
        logging.info( "Demo exiting" )

    def demoContinuous(self,count=-1):
        logging.info( "demoContinuous(%d) has been called" % count )
        self._count = count
        self._state = self.RUNNING

    def demoOnce(self):
        self.demoContinuous(1)

    def demoHalt(self):
        logging.info( "demoHalt has been called" )
        if self._state == self.RUNNING:
            self._state = self.HALT

    def proxCallback(self,taps):
        if   taps == 2: self._lightsRandom()
        elif taps == 3: self.demoOnce()
        elif taps == 4: self.demoContinuous()
        elif taps == 5: self.demoHalt()
        else:           logging.info( "Number of taps: %d" % taps )

    def stop(self):
        self._state = self.DIE

    def _lightsRandom(self):
        pattern = ledPatternFactory( 'RandomLights' )
        params = Params( pattern.editor )
        params.minutes = 2.0
        setLedPattern( pattern, params )

    def _lightsOff(self):
        pattern = ledPatternFactory( 'Off' )
        params = Params( pattern.editor )
        setLedPattern( pattern, params )

    def _drawRandom(self):
        boundingBox = [ (0.0, 0.0), (TABLE_WIDTH, TABLE_LENGTH) ]
        while True:
            if self._state == self.HALT:
                return
            sandable = sandables[ random.randint(0,len(sandables)-1) ]
            sand = sandableFactory( sandable )
            params = Params( sand.editor )
            params.randomize( sand.editor )
            try:
                chains = sand.generate( params )
                t, d, p = Chains.estimateMachiningTime( chains, boundingBox, MACHINE_FEED, MACHINE_ACCEL )
                if DRAW_TIME_MIN <= t <= DRAW_TIME_MAX:
                    break
                logging.info( "Tried %s but time was %d:%02d" % (sand,int(t/60),int(t)%60))
            except Exception as e:
                logging.warning( "Tried %s but failed with %s" % (sand,e))

        logging.info( "Drawing %s, estimated time %d:%02d" % (sand,int(t/60),int(t)%60))
        with mach.mach() as e:
            e.run( chains, boundingBox, MACHINE_FEED, TABLE_UNITS, MACHINE_UNITS )
        History.save( params, sandable, chains, "lastdemo" )

    def _drawWait(self):
        with mach.mach() as e:
            while self._state == self.RUNNING and not e.getState():
                time.sleep( POLLING_DELAY )

    def _drawHalt(self):
        with mach.mach() as e:
            e.stop()


class ProxSwitchThread(Thread):
    """
        GPIO listener thread for proximity switch 
        callback - gets passed the number of taps
        window - the timeframe in seconds
    """
    def __init__(self,callback,window=PROX_SWITCH_SECS):
        super(ProxSwitchThread, self).__init__()
        self.pin = PROX_PIN
        self.window = window 
        self.callback = callback
        self.q = deque( maxlen=window )

    def run(self):
        logging.info( "ProxSwitchThread active" )
        self.running = True
        while self.running:
            t = time.time()
            if self.pin.value:
                self.q.append( t )
            if len(self.q) and t - self.q[0] >= self.window:
                self.callback(len(self.q))
                self.q.clear()
            time.sleep( POLLING_DELAY )

        logging.info( "ProxSwitchThread exiting" )

    def stop(self):
        self.running = False


class MyHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self.demo = self.server.demo

    def handle(self):
        command, data = json.loads( self.request.recv(1024*10).decode('utf-8'))
        logging.debug( "Command: %s, %s" % (command, data))
        if command == 'status':
            pass
        elif command == 'demoOnce':
            self.demo.demoOnce()
        elif command == 'demoContinuous':
            self.demo.demoContinuous()
        elif command == 'demoHalt':
            self.demo.demoHalt()
        elif command == 'restart':
            self._restart()
        elif command == 'jobAdd':
            self._jobAdd(data)
        elif command == 'jobDelete':
            pass    # FIX: Finish code
        elif command == 'jobList':
            pass    # FIX: Finish code
        else:
            logging.warning( "Unknown command: %s" % command )
        self.request.send( bytes(json.dumps({'state':self.demo._state}), encoding='utf-8'))

    def _restart(self):
        self.server.stop()

    def _jobAdd(data):
        pass    # FIX: CODE ISN'T DONE

if __name__=="__main__":
    logging.basicConfig(format='%(asctime)s %(message)s',level=logging.INFO)
    logging.info( 'Starting the SandTable scheduler daemon' )
    
    demo = Demo()
    demo.start()

    # Start listening for taps from the proximity switch
    proxSwitch = ProxSwitchThread( demo.proxCallback )
    proxSwitch.start()

    # Start the background job scheduler (which potentially means start servicing jobs)
    scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults, timezone=utc)
    scheduler.start()

    # FIX: Kluge to clear out the scheduler and start a random drawing everyday at 3:00 am.
    def kluge():
        logging.info( "Kluge triggered" )
        if SCHEDULER_ENABLED:
            logging.info( "Running single demo" )
            demo.demoOnce()
        else:
            logging.info( "Schedule is disabled" )
        logging.info( "Kluge returned" )

    for job in scheduler.get_jobs():
        job.remove()
    job = scheduler.add_job(kluge, 'cron', hour=7 )

    # Start the socket server and listen for requests
    # Retry logic has been implemented because sometimes sockets don't release quickly
    logging.info( "Trying to listen on %s:%d" % (SCHEDULER_HOST,SCHEDULER_PORT))
    retries = 10
    server = None
    while retries > 0:
        try:
            server = StoppableTCPServer((SCHEDULER_HOST,SCHEDULER_PORT), MyHandler)
            logging.info( "SocketServer connected" )
            break
        except socket.error as e:
            logging.error( "%d retries left: %s" %(retries,e) )
            retries -= 1
            time.sleep(10.0)
    if server:
        server.demo = demo
        server.serve()
    logging.info( "Out of server loop!" )

    scheduler.shutdown()
    proxSwitch.stop()
    demo.stop()

    exit(1)
