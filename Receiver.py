'''
Base class that provides a thread for receiving from a (USB or serial) link and
 queuing inputs up for later consumption.
'''

import logging
import queue
import threading


class Receiver():
    def __init__(self, name=None):
        self.inputQ = queue.Queue()

        self.receiving = threading.Event()
        self.receiving.clear()
        self.closed = False

#        threading.Thread.__init__(self, name=name)
        self.receiverThread = threading.Thread(target=self.receiver, name=name)

    def __enter__(self):
        #### FIXME
        print("ENTER")

    def __exit__(self, type, value, tb):
        #### FIXME
        self.shutdown()

    def start(self):
        self.receiving.set()
        self.receiverThread.start()
        logging.debug(f"Starting thread: {self.receiverThread.name}")

    def shutdown(self, blocking=False):
        """Tell input thread to shutdown.

          Have to wait until 'closed' is set to be sure thread is shutdown.
        """
        if self.closed:
            logging.debug("Shutdown: already closed")
        self.receiving.clear()
        if blocking:
            self.waitForShutdown()

    def isShutdown(self):
        return self.closed

    def waitForShutdown(self):
        #### FIXME yield and wait until thread sets closed
        pass

    def receiver(self):
        """Decorator that wraps code that reads from a comm link and queues up
            the input.

          Loops until told to shutdown by the 'receiving' flag.
          Puts a final None value on the inputQ and indicates that its the input
           thread is done.
        """
        while self.receiving.isSet():
            inputs = self._receive()
            if inputs and 'data' in inputs and inputs['data']:
                try: 
                    logging.debug(f"Inputs: {inputs}")
                    self.inputQ.put_nowait(inputs)
                except Exception as ex:
                    logging.error(f"Input queue full, discarding input and shutting down: {ex}")
                    self.receiving.clear()
        self.inputQ.put(None)
        self.closed = True

    def _receive(self):
        raise NotImplementedError("Must define a method that reads the interface and puts on the 'inputQ'")

    def getInput(self):
        return self.inputQ.get()


#
# TEST
#
if __name__ == '__main__':
    print("Start")
    rx = Receiver()
    rx.shutdown()
    print("Done")

