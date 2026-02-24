"""
Timer CHOP Callbacks

me - this DAT

timerOp - the connected Timer CHOP
cycle - the cycle index
interrupt - True if the user initiated a premature, False if a result of a 
	normal timeout
fraction - the time in 0-1 fractional form

segment - an object describing the segment:
	can be automatically cast to its index: e.g.:  segment+3, segment==2, etc
	
	members of segment object:
		index     numeric order of the segment, from 0
		owner    Timer CHOP it belongs to
		
		lengthSeconds, lengthSamples, lengthFrames
		delaySeconds, delaySamples, delayFrames
		beginSeconds, beginSamples, beginFrames
		speed
"""
from datetime import datetime

def onCycle(timerOp: timerCHOP, segment: Segment, cycle: int):
	"""
	Called when a cycle completes.
	
	Args:
		timerOp: The connected Timer CHOP
		segment: The segment object
		cycle: The cycle index
	"""
	debug(datetime.now())

	return