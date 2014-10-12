Field-device---RTU
==================

IED - Intelligent

NEW MODIFICATIONS - 27:

- I edited the testbedinit.sh file to include downloading the python_simplejson. Might as well get everything we need.

-I edited the two run scripts to have a "master" and "slave" specific script

-I edited the mkconfig so that the logic emulated the control_microsystems_old, added the "_old".  Looking at his holding registers, they all look like 
 how he has the old system defined. That cleared up one error on the slave system.

-I had to add "sudo" before each of the terminal commands that start the python scripts in the run.sh file. Apparently, the "sudo true" at the beginning isn't enough. I never could open port 502(the ModbusTCP port) because of this. SOLVED.

-In order to run master and slave on different VMs, I had to add exceptions for the particular ports(TCP:502, UDP:9912, UDP:9913)

-In order to run master and slave on different VMs, I had to modify the config file. The master "simiface" receipient IP address needs to be the slave, and the slave's receipient IP address needs to be the master. Likewise, both the master "clientiface" and slave "icsiface" IP address needs to be the slave. 

-looks like my USB3.0 port isn't compatible with my VMWare Workstation 10 running Windows XP with a virtual USB3.0 controller. It does work when I put it on a USB2.0 hub and chagned the virtual USB controller to 2.0. This is needed to use the USB hardware key.

-The virtual slave PLC is defined as device 4 in the Modbus protocol. In order to get the ModbusTCP driver working on the XP machine(iFix), I had to get the right IP address for the slave PLC, the right device, and the right register set. The register set is 6 digit, and the first digit is 4(which translates into Modbus blocktype 3. Weird, I know), then the 5 digit address. The configuration is on the XP computer. The register set should be in the config file, and in the excel spreadsheet for the tcppipe simulation.

-In order to write to the slave PLC, I have to write in the location where the master PLC would write, so I've got the master PLC commented out of the shell script. This will probably change later when I reincorporate the master PLC

-For some reason, for any 1 bit data item I request from the slave PLC through iFix's MBE driver, it subtracts 1 bit from the address I give it. In order to compensate for this, I added 1 to every address I needed for 1 bit data items. The floats(2-bit) seem to work fine. Le weird.

-I modified the PIDSetpoint, PIDGain, and PIDRate values in the mkconfig script to have decimal places. Apparently, iFix struggles if it does have a defined decimal value and at least one non-zero value(thus for 0, I used 0.00001) 
 
-I think the command to open the port logger in the run.sh script actually opens the serial ports. Had to uncomment that one to use the RTU sims.

-I added installing glibc.i686 to the testbedinit file. I think we need it for the attack scripts.

-I edited the config file such that the SP starts up as 5.0 instead of 10.0.

-for Wei's attacks, I'mn using some serial-to-MODBUS converter code. Looks like I need to run "./mtu.out localhost". Right now, mtu.c is setup to listen on ttyS2. The attack code needs to be setup for it's output to be ttyS1. These are physical ports right now.  

-the serial-to-tcp converter is setup using the mtu.c. The attacks(which are mostly serial) write to serial port 2(which is setup as the client in VMWARE) and the mtu.c converter reads from serial port 3. It then converts this and connects to the IP address 10.128.0.1 port 502 and sends the serial data as TCP packets.

-I have a second VM just for running the attacks at IP 10.128.0.4 that has 2 "physical" serial ports

- I did modify the attacks that I'm using, and most of the attacks in the file. I changed to used the serial ports, and I changed the address of the register to be attacked. I suspect this is because I took the master out of the equation. I wrote my own variant of the SP attack that ONLY modifies the setpoint, not all the PID parameters. 

-I wrote a script to start up both the mtu.c and whichever of the 3 attacks I'm using.
 it's in the scripts folder as attack.sh

-I modified the mtu.c code so that it doesn't wait on a tcp response. Just grabs the serial data and converts/sends tcp data. I don't want a tcp RST packet to cause the converter to fail. Cause it did.

-i wrote my own HMI in an Python environment within Ubuntu.  It does need the modbus-tk library and python-tk for graphics. Should be under trunk and ZaxGraphics

-I think I'm gonna reincorporate the master PLC so I can try to have multiple slaves. Let's see. But I'm pretty sure the master is only a MODBUS client, not a MODBUS server. Gotta fix that first. This may mean rearchitecting Brad's whole system. Poopoo.

-Looks like the tcptank config also had to be modified. I don't know why, but he has his memory model as "control_microsystems" but all his addresses are for "control_microsystems_old". I changed it to "old" as well as the IP address to 10.128.0.1

-yeah, the tcptank is a really simple simulation. Like stupid, unusable, simple. I wonder if that's for the big tanks in the SCADA lab.

-created a tcpwater simulation. Just took his rtuwater and changed the config file for tcp. I think it's gonna work. Device ID 7 BTW.

-i modified the ports being used, because I wanna run multiple simulations at once. The tcpwater simulation now uses 9922,9923,and 503 instead of 9912, 9913, and 502.

-yeah, I had to modify the simulation.py script because it's written to look at the rtuwater config file. Not cool. Now it looks at the tcpwater config file.

-modifying the ports works for 2 slaves at once. Just have to tell the HMI to read from port 503 on the second simulation

-added "sudo yum install tkinter" to the init script. Need it for my python HMI

-I also added "wireshark", "wireshark-gnome", and "gcc-c++" to the init script cause we need them.

-modified the tcpwater config file to start in AUTO. this is because, no matter the mode, the water is always draining from the tank at a set rate. This is fine, but it keeps draining past 0%, and the sim starts at 0%, so we get negative numbers. It's a temp fix.

-added "gnome-terminal", "git", "gedit", had the scripts pull the repo, install snort, change the folder permissions, and add firewall exceptions

- I fixed the draining issue. The minimum level was set at -15% in the config file.  I moved that to 0% and put the startup mode back to OFF. So it just sits empty.

- I modified the addresses of the tcpwater simulation to match the real ground water PLC. I adjusted it in the HMI as well.  

OBSERVATIONS:

-The simulator runs on the same machine as the master. According to Bill. Le weird.

-For the tcppipe simulation, in AUTO - PUMP control, PSI higher than 7.28 cannot be acheived. In AUTO - SOLENOID control, SP lower than 7.28 cannot be achieved. 

-The master PLC is not currently written to be a MODBUS server. In order to accomplish Dr. Morris's goal, that will have to be modified. It is also noteworthy that the slave PLC is not written to be a MODBUS client. I don't think that mattters right now.

-In order to facilitate having each VirtualPLC being a MODBUS server, I think each virtualPLC needs to be on it's own VM.

