'''
Base class that provides a thread for receiving from a (USB or serial) link and
 queuing inputs up for later consumption.
'''

import logging
import queue
import threading
import time


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

    def shutdown(self, blocking=True):
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
        while not self.closed:
            time.sleep(1)

    def receiver(self):
        """Decorator that wraps code that reads from a comm link and queues up
            the input.

          Loops until told to shutdown by the 'receiving' event.
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

    def getInput(self, block=True, timeout=None):
        """Return input from the input queue.

          Can optionally be a blocking call, with an optional timeout

          Returns: next value from input queue, or None
        """
        inputVal = None
        if block:
            inputVal = self.inputQ.get()
        else:
            try:
                inputVal = self.inputQ.get(block=True, timeout=timeout)
            except:
                logging.debug("No input, blocking get() timed out")
        return inputVal


#
# TEST
#
if __name__ == '__main__':
    import time

    class DummyReceiver(Receiver):
        def __init__(self):
            self.count = 0
            super().__init__(name="DummyReceiver")
        def _receive(self):
            if self.count == 0:
                print("Running")
            self.count += 1

    #### FIXME add real tests
    logging.basicConfig(level="DEBUG",
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    print("Start")
    rx = DummyReceiver()
    rx.start()
    time.sleep(1)
    print("Shutting down")
    rx.shutdown()
    assert rx.isShutdown(), "Not shut down properly"
    print("Done")

