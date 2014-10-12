#!/usr/bin/env python

import socket, time, datetime
import sys, errno
import logging, unittest

"""
ifaces.py contains abstracted interfaces for communication between devices in
svt. Use these rather than hardcoding boilerplate code. See the virtual 
class for information about the methods and how to use these classes. """

class virtual():
    """Virtual class for communications interfaces

    This class is meant to be a virtual interface for the other communications 
    interfaces. Most methods here serve as placeholders. Each interface must
    implement an initialize() method, a getMessage() method, and a sendMessage()
    method. The methods are callable, so this can be a placeholder for
    developing other code.
    """
    def __init__(self, *args, **kwds):
        """Constructor for the interface. All constructors should implement
            variable length call parameters with *args and **kwds. These permit
            the actual configuration dictionaries to be passed to iface 
            constructors. The variable arguments will actually be used to catch
            configuration parameters that aren't used by the constructor. """
        pass

    def initialize(self, **kwds):
        """initialize() is used to set up the comm channel. It may be used to 
        call bind() or socket(), open or create a file or pipe descriptor, or
        other necessary task. Channel specific parameters, like filenames,
        source or destination addresses or ports, may be provided as 
        arguments"""
        pass
    def getMessage(self, block=True, timeout=None):
        """getMessage() is used to return a whole message (where possible) from
        the comm channel. The message may be a JSON update, an ICS protocol
        message, or other message.

        @param block Boolean. If true, this call blocks until timeout
        @param timeout Floating point value in seconds specifying how long the
                        call should block if parameter block is true. If none 
                        and block == True,  call will block indefinitely. If 
                        block is false, this value has no effect.

        @returns A string containing the contents of the message.
        """
        pass
    def sendMessage(self, message, recipients=None):
        """sendMessage() transmits the message provided in the call over the 
        channel.

        @param message A string containing the message to be sent. 
        @param recipients A list of device addresses or file descriptors to 
               write the message to. If the default None is used, the recipient
               will be the one(s) established in initialize().
        """
        pass

    def shutdown(self):
        """shutdown() closes relevant sockets, files, and otherwises cleans up
        the interface.""" 
        pass

class udp(virtual):
    """Interface to UDP communications.

    This class provides the common interface to a UDP socket. All constructor
    fields must be defined before calling initialize(), or the socket calls will
    fail."""
    def __init__(self, sport=None, recipients=None, timeout=None, **kwds  ):
        """udp interface constructor.

        @param sport local port to listen for information (bind())
        @param recipients list of tuples of form (ipaddress, port). If more than
                one recipient is listed, then calls to sendMessage() will send
                the message to each recipient in the list. A single tuple of
                form (ipaddress, port) can also be provided.
        @param timeout Float of number of seconds for a blocking getMessage
                        call to block. If None, calls will block indefinitely.
        """
        self.MAX_UDP_DATA_LEN= 65507 #According to wikipedia
        self.sport=sport
        self.recipients=recipients
        self.timeout=timeout

    def initialize(self):
        """ initializes a udp socket bind()ed to self.sport """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind( ('',self.sport) )
    
    def getMessage(self, block=True):
        """ Waits on a message to arrive from the UDP socket. 
            
            @param block Determines if calls will block until self.timeout or not. 
                        Default is to block.
            @throws socket.timeout If the timeout is reached before a message
                                    is received
            @throws socket.error If a non-blocking call has nothing to recieve.
                     value will be errno.EWOULDBLOCK. Non-blocking calls should
                     check the errno of the exception and reraise the exception
                     if it's not errno.EWOULDBLOCK
            @returns A string consisting of the received message, or None on 
                        timeout or socket.error.errnum==EWOULDBLOCK
        """
        if block:
            self.sock.settimeout(self.timeout)
            try:
                message, address = self.sock.recvfrom(self.MAX_UDP_DATA_LEN)
                return message
            except socket.timeout:
                return None

        else:
            self.sock.settimeout(0)
            try:
                message, address = self.sock.recvfrom(self.MAX_UDP_DATA_LEN)
                return message
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK: #I.e. there is nothing to recv
                    return None
                else: 
                    raise e #Raise exception to be dealt with at higher level
                    return None

    def sendMessage(self, message, recipients=None):
        """sends the parameter message to each recipients in the recipients
        list. If the function call argument is none, the class default is used.
        Otherwise, the argument supercedes the list defined by the class
        
        @param message A string to be sent over UDP to recipients
        @param recipients A list of tuples of form (ipaddress, port) to send the
                            message to
        """
        if recipients is None:
            recipients = self.recipients
        if isinstance(recipients, tuple):
            recipients = [recipients] # make the tuple a list for the next for:
        for address in recipients:
            self.sock.sendto(message, address) #Send message 

    def shutdown(self):
        """Closes the socket created in initialize()"""
        self.sock.close()

class tcp(virtual):
   ##TODO
   pass

class serial(virtual):
    ##TODO
    def __init__(*args, **kwds):
        pass
#--------------------- Unit tests ------------------------------
class UDPTest(unittest.TestCase):
    """\internal
    This class holds testcases for the UDP interface.
    """
    #Test UDP:
    def setUp(self):
        """Called at start of unit test. Initializes three udp interfaces
            on localhost"""
        #print '-'*20+'UDP Interface Test'+'-'*20
        #print '[+] Creating 3 UDP interfaces'
        self.u1 = udp(sport=1500, recipients=('127.0.0.1', 2500) )
        self.u2 = udp(sport =2500, recipients=[('127.0.0.1',1500),('127.0.0.1', 3500)] )
        self.u3 = udp(sport=3500, recipients=[('127.0.0.1', 1500)] ) 

        #print '[+] Initializing 3 UDP interfaces'
        self.u1.initialize()
        self.u2.initialize()
        self.u3.initialize()
    
    def testUnicastSend(self):
        #print '[+] Testing single unicast send'
        testmsg="This is a test message"
        self.u1.sendMessage(testmsg)
        rxd=self.u2.getMessage()
        self.assertEqual(testmsg, rxd)
        del rxd

    def testMulticastSend(self):
        #print '[+] Testing "multicast" send'
        testmsg="This is a test message"
        self.u2.sendMessage(testmsg)
        rxd1=self.u1.getMessage()
        rxd3=self.u3.getMessage()
        self.assertEqual(testmsg, rxd1)
        self.assertEqual(testmsg, rxd3)
        #if rxd1 == rxd3 == testmsg:
        #    print "\t[+]Test Succeeded"
        #else:
        #    print "\t[+]Test Failed"
        del rxd1
        del rxd3

    def testRecipientChange(self):
        #print '[+] Testing recipient override'
        testmsg="This is a test message"
        self.u1.sendMessage(testmsg, recipients=[('127.0.0.1', 2500), ('127.0.0.1', 3500)])
        rxd2=self.u2.getMessage()
        rxd3=self.u3.getMessage()
        self.assertEqual(testmsg,rxd2)
        self.assertEqual(testmsg,rxd3)
#        if rxd2 == rxd3 == testmsg:
#            print "\t[+]Test Succeeded"
#        else:
#            print "\t[+]Test Failed"
        del rxd2
        del rxd3
    
    def testTimeout(self):
        for t in range(1,10,2):
            self.u1.timeout=t
            last = time.time()
            #no message was sent, so this should time out
            self.u1.getMessage(block=True)
            self.assertTrue(time.time() - last > (self.u1.timeout - 1))
            self.assertTrue(time.time() - last < (self.u1.timeout + 1))
    
    def testNonBlockingGetMessage(self):
        #Nothing should happen -- the call should return immediately
        self.u1.getMessage(block=False)

    def testMultiSendMultiRx(self):
        #print "[+] Testing multiple sends and multiple receives"
        msg1 = 'One'
        msg2 = 'Two'
        self.u1.sendMessage(msg1, recipients=('127.0.0.1', 2500))
        self.u1.sendMessage(msg2, recipients=('127.0.0.1', 2500))
        
        rxd1=self.u2.getMessage()
        rxd2=self.u2.getMessage()
        self.assertEqual(rxd1,msg1)
        self.assertEqual(rxd2,msg2)

    def tearDown(self):
        #print '[+] Testing shutdown'
        self.u1.shutdown() 
        self.u2.shutdown() 
        self.u3.shutdown() 


if __name__ == "__main__":
    unittest.main()
