#!/usr/bin/env python
# vim:tw=80

#Built-in imports
import logging
import unittest
from serial import Serial

#Module imports
from point import Point

#External imports
import modbus_tk
from modbus_tk import modbus_tcp, modbus_rtu
from modbus_tk import defines as modbus_defines

if not hasattr(modbus_tk, '_VTB_MODBUS_TK_'): 
    #TODO: Make this a log entry someday
    print "WARNING: Using installed Modbus-TK. Testbed patches are not present."
    

#Note: The imports assume that this file is being executed from the trunk
#       directory. To run from the command line: 
#       [sudo] python -m protolibs.ics-servers

class ICSServer(object):
    """Abstract base class for ICS protocol servers"""
    def __init__(self, *args, **kwds):
        """Initializes the ICSServer from configuration information"""
        raise NotImplementedError()

    def start(self):
        """Called to start any necessary threaded objects"""
        raise NotImplementedError()

    def stop(self):
        """Called to stop any necessary threaded objects"""
        raise NotImplementedError()
    def exit(self):
        """Calls self.stop(). This is implemented to be compatible 
            with threads"""
        self.stop()
        
class Modbus(ICSServer):
    """Wrapper for modbus servers in the modbus-tk library. Since differences
        in modbusTCP and modbus RTU are minimal, this class holds the majority
        of the modbus server logic."""
    def __init__(self, icsconfig, points, *args, **kwds):
        """ Initializes the ModbusTCP server.
        @param icsconfig The dictionary containing interface information from
                            from the configuration file. 
        @param points List of point objects from the vdev.
        """
        LOGGER = logging.getLogger("modbus_tk")
        self.server = self._make_server(icsconfig)
        self.slave = self.server.add_slave(icsconfig['id'])
        self._add_points(points, icsconfig['memory_model'])
        
    def start(self):
        """Called to start the server thread"""
        LOGGER = logging.getLogger("modbus_tk")
        self.server.start()

    def stop(self):
        """Called to stop the server thread"""
        self.server.stop()

    def _add_points(self, points, memory_model):
        """Adds references to the vdev points to the ICS protocol server
            memory model.
            @param points List of points relevant to this interface
            @oaram memory_model 
            """
        ##Create memory model
        #@TODO: Get memory model for other devices
        if memory_model == 'control_microsystems':
            #Addresses taken from:
                #http://www.controlmicrosystems.com/resources-2/faqs/telepace4/
            self.slave.add_block('coil', modbus_defines.COILS, 1, 4096)
            self.slave.add_block('statusreg', modbus_defines.COILS, 10001, 14096)
            #Inputregs should be a 16-bit input register
            self.slave.add_block('inputreg', modbus_defines.ANALOG_INPUTS, 30001, 31024)
            self.slave.add_block('holdingreg', modbus_defines.HOLDING_REGISTERS, 40001, 
                                    49999)
        else:
            #default Memory model    
            self.slave.add_block('coil', modbus_defines.COILS, 0, 100)
            self.slave.add_block('hreg', modbus_defines.HOLDING_REGISTERS, 100, 100)
            self.slave.add_block('idisc', modbus_defines.DISCRETE_INPUTS, 200, 100)
            self.slave.add_block('ireg', modbus_defines.ANALOG_INPUTS, 300, 100)

        ##Place points into modbus blocks
        for pt in points:
            addr = int(  pt.metadata['modbus']['addr'] )
            blockname = pt.metadata['modbus']['blockname']
            self.slave.set_values(blockname, addr, pt)
            #assert(pt.get() == self.slave.get_values(typ, addr, 0), 
            #            "Point set unsuccessfully")
    def _make_server(self, icsconfig):
        """Used to create an appropriate Modbus RTU or TCP server object"""
        raise NotImplementedError()

class ModbusTCP(Modbus):
    """Creates a ModbusTCP server object""" 
    def _make_server(self, icsconfig):
        """ Creates a self.server object based on the icsconfig
        @param icsconfig Configuration information about this interface. This
                            is the 'icsifaces' dictionary in the config.
        @returns A TCP Server object
        """
        server = modbus_tcp.TcpServer(port=icsconfig['port'], 
                                      address=icsconfig['address'])
        return server

class ModbusRTU(Modbus):
    """Creates a ModbusRTU server object""" 
    def _make_server(self, icsconfig):
        """ Creates a self.server object based on the icsconfig
        @param icsconfig Configuration information about this interface
        @returns An RTU Server object
        """
        serial = Serial()
        serial.port = icsconfig['port']
        serial.baudrate = icsconfig['baudrate']
        serial.open()
        server = modbus_rtu.RtuServer(serial)
        return server

class ModbusTCPTest():
    """@ internal
       Contains methods for testing a ModbusTCP server. Subclassing unittest 
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


    def testPolling(self):
        import time
        time.sleep(2)
        import modbus_tk.modbus_tcp as modbus_tcp
        master = modbus_tcp.TcpMaster(self.port)
        master.set_timeout(2.0)
        v = master.execute(1, modbus_defines.READ_INPUT_REGISTERS, 30001, 3)
        print "BRDEBUG: Reply: ", v
        assert v[1] == 20
        assert v[0] == 17
        assert v[2] == 0
        v = master.execute(1, modbus_defines.READ_HOLDING_REGISTERS, 40001, 1)
        print "BRDEBUG: Reply: ", v
        assert v[0] == 15
        master.execute(1, modbus_defines.WRITE_SINGLE_REGISTER, 40001, output_value=54)
        v = master.execute(1, modbus_defines.READ_HOLDING_REGISTERS, 40001, 3)
        assert v[0] == 54
    
    
    def tearDown(self):
        self.server.stop()
        pass

    def setUp(self):
        """This method can be called externally to set up a server for 
                testing."""
        import modbus_tk.modbus_tcp as modbus_tcp
        self.port = 31337
        icsConfig = {
                'name' : 'Modbus',
                'memory_model' : 'control_microsystems',
                'typ' : 'modbusASCII',
                'id' : 1,
                'port' : self.port,
                'address' : '127.0.0.1'
               }

        p1 = Point(**{'name':'pressure','typ':1, 'value':20, 
                    'metadata':{'modbus':{ 'addr':'30002', 'blockname':'inputreg',
                                    'blocktype':4}}})
        p2 = Point(**{'name':'pressure','typ':1, 'value':17, 
                    'metadata':{'modbus':{ 'addr':'30001', 'blockname':'inputreg',
                                    'blocktype':4}}})

        p3 = Point( **{'name':'setpoint',  'typ':0, 'value':15, 
                    'metadata':{'modbus':{ 'addr':'40001', 'blockname':'holdingreg',
                                    'blocktype':3}}} )
        points = [p1, p2, p3]
        self.server = ModbusTCP( icsConfig, points)
        self.server.start()
    def run(self):
        try:
            self.setUp()
        except Exception as e:
            print "Test failed: Unable to set up test"
            print str(type(e)),' ',str(e)
            self.print_tb()
            return False
        try:
            import time
            time.sleep(2)
            self.testPolling()
        except Exception as e:
            print "Test failed: Unable to test polling"
            print str(type(e)),' ',str(e)
            self.print_tb()
            return False
        finally:
            try:
                self.tearDown()
            except Exception as e:
                print "Test failed: Unable to tear down test"
                print str(type(e)),' ',str(e)
                self.print_tb()

        print "Test passed"
        return True

class ModbusRTUTest():
    """@ internal
       Contains methods for testing a ModbusTCP server. Subclassing unittest 
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


    def testPolling(self):
        import time
        time.sleep(2)
        import modbus_tk.modbus_rtu as modbus_rtu
        
        master_port = Serial('./pty/0', baudrate=19200)
        master = modbus_rtu.RtuMaster(master_port)
        #master.set_timeout(2.0)
        v = master.execute(1, modbus_defines.READ_INPUT_REGISTERS, 30001, 3)
        print "BRDEBUG: Reply: ", v
        assert v[0] == 17
        assert v[1] == 20
        assert v[2] == 0
        v = master.execute(1, modbus_defines.READ_HOLDING_REGISTERS, 40001, 1)
        print "BRDEBUG: Reply: ", v
        assert v[0] == 15
        master.execute(1, modbus_defines.WRITE_SINGLE_REGISTER, 40001, output_value=54)
        v = master.execute(1, modbus_defines.READ_HOLDING_REGISTERS, 40001, 3)
        assert v[0] == 54
    
    
    def tearDown(self):
        self.server.stop()
        pass

    def setUp(self):
        """This method can be called externally to set up a server for 
                testing."""
        import modbus_tk.modbus_tcp as modbus_tcp

        icsConfig = {
                'name' : 'Modbus',
                'memory_model' : 'control_microsystems',
                'typ' : 'ModbusRTU',
                'id' : 1,
                'port' : './pty/1',
                'baudrate' : 19200
               }

        p1 = Point(**{'name':'pressure2','typ':1, 'value':20, 
                    'metadata':{'modbus':{ 'addr':'30002', 'blockname':'inputreg',
                                    'blocktype':4}}})
        p2 = Point(**{'name':'pressure','typ':1, 'value':17, 
                    'metadata':{'modbus':{ 'addr':'30001', 'blockname':'inputreg',
                                    'blocktype':4}}})

        p3 = Point( **{'name':'setpoint',  'typ':0, 'value':15, 
                    'metadata':{'modbus':{ 'addr':'40001', 'blockname':'holdingreg',
                                    'blocktype':3}}} )
        points = [p1, p2, p3]
        self.server = ModbusRTU( icsConfig, points)
        self.server.start()
    def run(self):
        try:
            self.setUp()
        except Exception as e:
            print "Test failed: Unable to set up test"
            print str(type(e)),' ',str(e)
            self.print_tb()
            return False
        try:
            import time
            time.sleep(2)
            self.testPolling()
        except Exception as e:
            print "Test failed: Unable to test polling"
            print str(type(e)),' ',str(e)
            self.print_tb()
            return False
        finally:
            try:
                self.tearDown()
            except Exception as e:
                print "Test failed: Unable to tear down test"
                print str(type(e)),' ',str(e)
                self.print_tb()

        print "Test passed"
        return True
if __name__ == '__main__':
    #test=ModbusTCPTest()
    test=ModbusRTUTest()
    test.run()
    #import code
    #code.interact (local = locals())
