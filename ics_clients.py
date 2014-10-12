#!/usr/bin/env python
# vim:tw=80

"""
ics-clients.py 

Contains client objects for each of the implemented ICS protocols. 
A client is an object that permits polling of an ICS server. Essentially,
clients generate requests. Masters will typically use client objects,
while slave communications will be based from servers. 
"""

from serial import Serial
import logging

import modbus_tk
import modbus_tk.defines as cst
import modbus_tk.modbus_tcp as modbus_tcp
import modbus_tk.modbus_rtu as modbus_rtu

LOGGER = logging.getLogger("modbus_tk")
LOGGER.setLevel(logging.DEBUG)
LOGGER.addHandler(logging.FileHandler('/tmp/icsclient.log'))

if not hasattr(modbus_tk, '_VTB_MODBUS_TK_'): 
    #TODO: Make this a log entry someday
    print "WARNING: Using installed Modbus-TK. Testbed patches are not present."

class ICSClient(object):
    """Abstract base class for ICS protocol clients.
    Because there may be confusion between similarly named servers and
    clients, the client defines a class member _CLIENT, which
    can be checked at runtime."""
    _CLIENT = True 
    def __init__(self, to_config, slave_points, from_config=None):
        """Initializes the ICS client from configuration information"""
        raise NotImplementedError()

    def readPoints(self, points):
        """Method to return points from a given device. A single call to this
            method will generate one or more protocol requests of the server of
            objects. Inheriting clients will interpret the best way to request 
            each point, whether it be individually or in groups. This is
            necessary to provide a neutral interface to different ICS protocols.
            Each protocol has different semantics towards polling values of
            points.
        @param device Name of the device to be polled
        @param points Iterable of names of points to be polled
        
        @returns A tuple of values of the points polled in the order that they
                    were requested.
        """
        raise NotImplementedError()

    def writePoints(self, pointsvalues):
        """Method to set points on a given device. A single call to this
            method will generate one or more protocol requests of the server of
            objects. Inheriting clients will interpret the best way to write each
            point, whether it be individually or in groups. Base clients 
        @param device Name of the device to be polled
        @param pointsvalues List of tuples of (names of point to be written,
                                value)
        """
        raise NotImplementedError()


    class ICSClientException(Exception):
        """Base class for the exceptions thrown by the icsClient"""
        pass

    class NoSuchPointError(ICSClientException):
        """Exception thrown when a point is read or written that doesn't exist
            on the server"""
        pass
        
        

class ModbusClient(ICSClient):
    """Parent class for the TCP and RTU varieties of ModbusClients. This class
        implements most of the logic for creating Modbus requests. Child classes
        need only implement the _createMaster method for the proper request type"""
    MAXDISTANCE = 5 # Max distance is used when forming requests. Basically,
                        # if two points' addresses are at most MAXDISTANCE
                        # apart, one request will be used for both, and
                        # intermediate values will be discarded. Otherwise, two
                        # separate requests will be sent
    FUNCTION_MAP={ cst.COILS: (cst.READ_COILS,cst.WRITE_SINGLE_COIL, 
                                                cst.WRITE_MULTIPLE_COILS),
                      cst.DISCRETE_INPUTS : (cst.READ_DISCRETE_INPUTS, 
                                                None, None),
                      cst.HOLDING_REGISTERS : (cst.READ_HOLDING_REGISTERS, 
                                                cst.WRITE_SINGLE_REGISTER, 
                                               cst.WRITE_MULTIPLE_REGISTERS),
                      cst.ANALOG_INPUTS : (cst.READ_INPUT_REGISTERS, 
                                                None, None) 
                   }
    def __init__(self, to_config, slave_points, from_config=None):
        """Initializes the client from configuration information.
        @param to_config The configuration for the interface on the slave to
                            poll. 
        @param from_config The configuration for the interface on the master 
                            to poll from. This is ignored for TCP but required
                            for RTU.
        @param slave_points The points list from the slave configutation
        """

        self.to_config = to_config
        self.from_config = from_config
        self.slave_points = slave_points
        self.master = self._createMaster()
        
    def _createMaster(self, *args, **kwds):
        """Child classes will override this method to provide the correct 
            type of master -- TCP or RTU"""
        raise NotImplementedError
   
    def _requestPoints(self, points, rw, values=None):
        """Method to implement reading and writing points from a given device.
            A single call to this
            method will generate one or more protocol requests of the server of
            objects. Clients will interpret the best way to request each
            point, whether it be individually or in groups.
        @param points Iterable of names of points to be polled
        @param rw Whether this is a read request or a write request.
                    'r' indicates read, 'w' indicates write.
        @param values Dictionary of pointName:value pairs to write
        
        @returns If a read request, returns a tuple of values of the points 
                    polled in the order that they were requested.
        """
        ##Argument validation: 
        if rw!='r' and rw!='w':
            message = "Unsupported operation %s for _requestPoints" % rw
            raise Exception(message)
        slaveAddress = self.to_config['id']
        
        ## Prepare points and values for updates
        #Group points by block types 
        pointsByType = {cst.COILS:[], cst.DISCRETE_INPUTS:[],
                        cst.HOLDING_REGISTERS:[], cst.ANALOG_INPUTS:[]}

        if not hasattr(points, '__iter__'): #make points iterable
            points = [points] 
        #Make a list of point descriptions of the points we should read
        for ptdesc in [pt for pt in self.slave_points if pt['name'] in points]:
            pointtype=ptdesc['metadata']['modbus']['blocktype'] 
            pointsByType[pointtype].append(ptdesc)
         

        #Shortcut lambdas
        getaddr = lambda p: int( p['metadata']['modbus']['addr'] )
            # Quick function to compare if two points are close enough to place in
            # the same packet
        closeenough = lambda p,q: getaddr(p) - getaddr(q) <=\
                            (self.MAXDISTANCE if rw=='r' else 1)

        ## Go through point types and create send proper requests
        replies={} #store replies by the name of the point they correspond to
        for pointType in pointsByType.keys(): 
            # We sort by address so that to see how close consecutive points are
            pointsByType[pointType].sort(key = getaddr) 

            # Iterate over all the points of this type. Make a list of all the
            # ones that are close together, and request them all at once. To
            # keep track of them, we're putting the name of the point and the
            # reply offset in a tuple in this list.

            requestPoints = []
            for index, pt in enumerate(pointsByType[pointType]):
                if len(requestPoints) == 0: #We're adding a first point
                    reqBaseAddr =  getaddr(pt)
                    reqOffset = 0
                else: 
                    reqOffset = getaddr(pt) - reqBaseAddr 
                requestPoints.append((pt['name'], reqOffset, pt))

                try:
                    nextPoint = pointsByType[pointType][index+1]
                    endOfGroup = not closeenough( pt, nextPoint) 
                except IndexError: #We're at the end of the list
                    endOfGroup = True

                if endOfGroup: ##Send request:
                    startAddress = getaddr(requestPoints[0][2])
                    commandType = 0 if rw=='r' else 2 if len(requestPoints)>1 else 1
                    args = [slaveAddress, 
                            self.FUNCTION_MAP[pointType][commandType],
                            startAddress]
                    if rw=='r': 
                        numberOfItems = requestPoints[-1][1] + 1
                        reply = self.master.execute(*args, quantity_of_x=numberOfItems)
                        #Parse the reply for the values of the specific points we want
                        generator = ( (t[0], reply[t[1]]) for t in requestPoints )
                        replies.update(generator)
                    else: #rw == 'w'
                        if len(requestPoints)>1:
                            output_value = [values[p[0]] for p in requestPoints]
                        else: output_value = values[requestPoints[0][0]]
                        reply = self.master.execute(*args, output_value=output_value)
                    requestPoints = []
        ## Return the replies in the proper order if read mode, None if write mode
        return tuple( [replies[name] for name in points] ) if rw == 'r' else None


        # \bug If points are requested to be written that aren't writable in
        # Modbus, an exception is thrown. Something smart may need to be done to
        # fix this.

    def readPoints(self, points):
        """Method to return points from a given device. A single call to this
            method will generate one or more protocol requests of the server of
            objects. Inheriting clients will interpret the best way to request each
            point, whether it be individually or in groups.
        @param device Name of the device to be polled
        @param points Iterable of names of points to be polled
        
        @returns A tuple of values of the points polled in the order that they
                    were requested.
        """
        return self._requestPoints(points, 'r')


    def writePoints(self, pointsvalues):
        """Method to set points on a given device. A single call to this
            method will generate one or more protocol requests of the server of
            objects. Inheriting clients will interpret the best way to write each
            point, whether it be individually or in groups. Base clients 
        @param pointsvalues List of tuples of (names of point to be written,
                                value) or a dictionary of {pointnames:values}
        """
        try: values = dict(pointsvalues)
        except ValueError: 
            #If pointsvalues is not a list, we get a ValueError
            values = dict([pointsvalues])
        points = values.keys()
        return self._requestPoints(points, 'w', values)

class ModbusTCP(ModbusClient):
    """This class provides an interface for a ModbusTCP Master."""

    def _createMaster(self):
        """Each slave will have a different address, so a master object will be
            required for each one. This method looks up the slave device's info
            in the configuration and creates a master object that will connect
            to it.
            @returns a modbus TCP master object
            """

        host = self.to_config['address']
        port = self.to_config['port']
        master = modbus_tcp.TcpMaster(host=host, port=port,
                        timeout_in_sec=10.0) #@TODO: Put timeout in configuration
        return master

class ModbusRTU(ModbusClient):
    """This class provides an interface for a ModbusRTU Master"""

    def _createMaster(self):
        """Each slave will have a different address, so a master object will be
            required for each one. This method looks up the slave device's info
            in the configuration and creates a master object that will connect
            to it.
            @returns a modbus RTU master object
            """
        port = self.from_config['port']
        baudrate = self.from_config['baudrate']
        master_port = Serial(port, baudrate=baudrate)
        master = modbus_rtu.RtuMaster(master_port)
        master.set_timeout(10)
        return master

def ICSClientFactory(full_config, slave_device, master_device, icsifaceIndex=0):
    """Factory used to instantiate an ICS client from a config object.
        The configuration is read to choose which type of ICS client should be
        used, and an appropriate ICS client object is returned.

        @param full_config Configuration dictionary for the whole testbed
        @param slave_device name of the device that will be queried
        @param master_device name of the device that will do the querying
        @param icsifaceIndex Index of the interface we want to use in the 
                                list of icsifaces for this device
        @returns The appropriate ICS client object for the device.
        """
    
     
    slave_config = full_config['vdevs'][slave_device]
    master_config = full_config['vdevs'][master_device]
    if not slave_config['icsifaces']:
        return None #NOTE: We may want an exception thrown here
    
    to_config = slave_config['icsifaces'][icsifaceIndex]
    if master_config['icsifaces']:
        from_config = master_config['icsifaces'][icsifaceIndex]
    else:
        from_config = None

    className = to_config['typ']
    cls = globals()[className] #Gets class from this module
    return cls(to_config, slave_config['points'], from_config)

class ModbusTCPTest():
    """@ internal
       Contains methods for testing a ModbusTCP client. Subclassing unittest 
            didn't work  with the master-slave network paradigm for some reason.
        To run, use create a new ModbusTCPTest object and call runTest(). This
        method will return True if the test passes, false otherwise. It will
        catch errors and exit gracefully. 
        
        Be sure the Python interpreter has root priviledges in order to open
        port 502.
    """
    def print_tb(self):
         import traceback
         import sys
         print '-'*60
         print 'Traceback:'
         traceback.print_tb(sys.exc_traceback)
         print '-'*60

    def testICSFactory(self, point = 'pressure', expectedValue = 17 ):
        """Test reading a single point using the ICS factory"""
        import time
        time.sleep(2)
        client = ICSClientFactory(self.config, 'slave', 'master') 

        reply = client.readPoints(point)
        #print "Slave pressure: ", reply
        assert reply[0] == 17

    def testSingleRead(self, point = 'pressure', expectedValue = 17 ):
        """Test reading a single point"""
        import time
        time.sleep(2)
        client = ModbusTCP(self.config['vdevs']['slave']['icsifaces'][0],
            self.config['vdevs']['slave']['points']) 

        reply = client.readPoints(point)
        #print "Slave pressure: ", reply
        assert reply[0] == 17

    def testAllRead(self):
        """Test reading all points"""
        import time,copy
        time.sleep(2)
        client = ModbusTCP(self.config['vdevs']['slave']['icsifaces'][0],
            self.config['vdevs']['slave']['points']) 

        pts = copy.deepcopy(self.config['vdevs']['slave']['points'])
        ptnames = [ pt['name'] for pt in pts ]
        reply = client.readPoints(ptnames)
        #print "Reply: ", reply
        for pt in ptnames:
            value = filter(lambda x: x['name']==pt, pts)[0]['value']
            #assert value == reply[ptnames.index(pt)]
            received = reply[ptnames.index(pt)]
            if not value == received: 
                print pt, ' was %s but should be %s'%(str(received),str(value))

    def testAllWrite(self):
        """Test writing all writable points"""
        import time,copy
        time.sleep(2)
        client = ModbusTCP(self.config['vdevs']['slave']['icsifaces'][0],
            self.config['vdevs']['slave']['points']) 

        pts = copy.deepcopy(self.config['vdevs']['slave']['points'])
        pts = [pt for pt in pts if pt['name']!='pressure'] #Can't write to pres
        ptnames = [ pt['name'] for pt in pts ]
        pointsvalues = dict(zip(ptnames, [0]*len(ptnames)))
        reply = client.writePoints(pointsvalues)
        assert reply is None, "Write returned value other than None: " + str(reply)
        reply = client.readPoints(ptnames)
        #print "Reply: ", reply
        for pt in ptnames:
            #assert value == reply[ptnames.index(pt)]
            if not 0 == reply[ptnames.index(pt)]: 
                print pt, ' was not read properly.'

    def testSingleWrite(self, point = 'setpoint', newValue = 54):
        """Test writing a single point"""
        import time
        time.sleep(2)
        client = ModbusTCP(self.config['vdevs']['slave']['icsifaces'][0],
            self.config['vdevs']['slave']['points']) 
        reply = client.writePoints((point,newValue))
        assert reply is None, "Write returned value other than None: " + str(reply)
        reply = client.readPoints(point)
        assert reply[0] == newValue

    def tearDown(self):
        self.server.stop()

    def setUp(self):
        """This method sets up a server for testing"""
        import protolibs.ics_servers as ics_servers
        from point import Point
        from configobj import ConfigObj

        # Get config file
        configfile = '/'.join(['sims', 'tank', 'config'])
        config=ConfigObj(infile=configfile, unrepr=True)
        self.config = config
        #Set global variable devconfig here 
        devconfig=config['vdevs']['slave'] 

        ##--Set up points
        points={}
        for p in devconfig['points']:
            points.update( { p['name'] : Point(**p) } ) 
            #The ** treats the p dictionary as the arguments to the Point class
        self.server = ics_servers.ModbusTCP( devconfig['icsifaces'][0], points.values() )
        self.server.start()

    def runtest(self, _test):
        try:
            self.setUp()
        except Exception as e:
            print "Test failed: Unable to set up test"
            print e
            return False
        try:
            import time
            time.sleep(2)
            _test()
        except Exception as e:
            print "Test failed: Unable to test ", _test.__doc__
            print str(type(e)),' ',str(e)
            self.print_tb()
            return False
        finally:
            try:
                self.tearDown()
            except Exception as e:
                print "Test failed: Unable to tear down test"
                print e

        print "Test passed: ", _test.__doc__

        return True

class ModbusRTUTest():
    """@ internal
       Contains methods for testing a ModbusRTU client. Subclassing unittest 
            didn't work  with the master-slave network paradigm for some reason.
        To run, use create a new ModbusRTUTest object and call runTest(). This
        method will return True if the test passes, false otherwise. It will
        catch errors and exit gracefully. 
        
        Ensure that the proper serial ports exist before running.
    """
    def print_tb(self):
         import traceback
         import sys
         print '-'*60
         print 'Traceback:'
         traceback.print_tb(sys.exc_traceback)
         print '-'*60

    def testICSFactory(self, point = 'pressure', expectedValue = 17 ):
        """Test reading a single point using the ICS factory"""
        import time
        time.sleep(2)
        client = ICSClientFactory(self.config, 'slave', 'master') 

        reply = client.readPoints(point)
        #print "Slave pressure: ", reply
        assert reply[0] == 17

    def testSingleRead(self, point = 'pressure', expectedValue = 17 ):
        """Test reading a single point"""
        import time
        time.sleep(2)
        to_config = self.config['vdevs']['slave']['icsifaces'][0]
        from_config = self.config['vdevs']['master']['icsifaces'][0]
        points = self.config['vdevs']['slave']['points']
        client = ModbusRTU(to_config, points, from_config)

        reply = client.readPoints(point)
        #print "Slave pressure: ", reply
        assert reply[0] == 17

    def testAllRead(self):
        """Test reading all points"""
        import time,copy
        time.sleep(2)
        to_config = self.config['vdevs']['slave']['icsifaces'][0]
        from_config = self.config['vdevs']['master']['icsifaces'][0]
        points = self.config['vdevs']['slave']['points']
        client = ModbusRTU(to_config, points, from_config)


        pts = copy.deepcopy(self.config['vdevs']['slave']['points'])
        ptnames = [ pt['name'] for pt in pts ]
        reply = client.readPoints(ptnames)
        #print "Reply: ", reply
        for pt in ptnames:
            value = filter(lambda x: x['name']==pt, pts)[0]['value']
            #assert value == reply[ptnames.index(pt)]
            received = reply[ptnames.index(pt)]
            if not value == received: 
                print pt, ' was %s but should be %s'%(str(received),str(value))

    def testAllWrite(self):
        """Test writing all writable points"""
        import time,copy
        time.sleep(2)
        to_config = self.config['vdevs']['slave']['icsifaces'][0]
        from_config = self.config['vdevs']['master']['icsifaces'][0]
        points = self.config['vdevs']['slave']['points']
        client = ModbusRTU(to_config, points, from_config)

        pts = copy.deepcopy(self.config['vdevs']['slave']['points'])
        pts = [pt for pt in pts if pt['name']!='pressure'] #Can't write to pres
        ptnames = [ pt['name'] for pt in pts ]
        pointsvalues = dict(zip(ptnames, [0]*len(ptnames)))
        reply = client.writePoints(pointsvalues)
        assert reply is None, "Write returned value other than None: " + str(reply)
        reply = client.readPoints(ptnames)
        #print "Reply: ", reply
        for pt in ptnames:
            #assert value == reply[ptnames.index(pt)]
            if not 0 == reply[ptnames.index(pt)]: 
                print pt, ' was not read properly.'

    def testSingleWrite(self, point = 'setpoint', newValue = 54):
        """Test writing a single point"""
        import time
        time.sleep(2)
        to_config = self.config['vdevs']['slave']['icsifaces'][0]
        from_config = self.config['vdevs']['master']['icsifaces'][0]
        points = self.config['vdevs']['slave']['points']
        client = ModbusRTU(to_config, points, from_config)

        reply = client.writePoints((point,newValue))
        assert reply is None, "Write returned value other than None: " + str(reply)
        reply = client.readPoints(point)
        assert reply[0] == newValue

    def tearDown(self):
        self.server.stop()

    def setUp(self):
        """This method sets up a server for testing"""
        import protolibs.ics_servers as ics_servers
        from point import Point
        from configobj import ConfigObj

        # Get config file
        configfile = '/'.join(['sims', 'tank', 'config'])
        config=ConfigObj(infile=configfile, unrepr=True)
        self.config = config
        #Set global variable devconfig here 
        devconfig=config['vdevs']['slave'] 

        ##--Set up points
        points={}
        for p in devconfig['points']:
            points.update( { p['name'] : Point(**p) } ) 
            #The ** treats the p dictionary as the arguments to the Point class
        self.server = ics_servers.ModbusRTU(devconfig['icsifaces'][0], points.values())
        self.server.start()

    def runtest(self, _test):
        try:
            self.setUp()
        except Exception as e:
            print "Test failed: Unable to set up test"
            print e
            return False
        try:
            import time
            time.sleep(2)
            _test()
        except Exception as e:
            print "Test failed: Unable to test ", _test.__doc__
            print str(type(e)),' ',str(e)
            self.print_tb()
            return False
        finally:
            try:
                self.tearDown()
            except Exception as e:
                print "Test failed: Unable to tear down test"
                print e

        print "Test passed: ", _test.__doc__

        return True

if __name__ == '__main__':
    tests = ModbusRTUTest()
    #tests = ModbusTCPTest()
    tests.runtest(tests.testICSFactory)
    tests.runtest(tests.testSingleRead)
    tests.runtest(tests.testSingleWrite)
    tests.runtest(tests.testAllRead)
    tests.runtest(tests.testAllWrite)
    #import code
    #code.interact(local=locals())

