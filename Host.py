'''
Object that encapsulates a USB connection to a CNC application running on a
 host processor.
'''

import logging

import hid

from Receiver import Receiver


#### FIXME implement this
class Host(Receiver):
    def __init__(self):
        super().__init__(name="Pendant")


#
# TEST
#
if __name__ == '__main__':
    raise NotImplementedError("TBD")

