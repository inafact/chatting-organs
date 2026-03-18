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
import json

def onCycle(timerOp: timerCHOP, segment: Segment, cycle: int):
	"""
	Called when a cycle completes.
	
	Args:
		timerOp: The connected Timer CHOP
		segment: The segment object
		cycle: The cycle index
	"""
	_now : datetime = datetime.now()
	_preschedule = json.loads(op("/project1/main_app/play_schedule").text)

	if _now.hour >= 17:
		# - Force night mode
		op("/project1/main_app").NightMode.val = True
	
	if _now.hour == 19 and _now.minute == 0 and _now.second < 3:
		# - exhibition closing task
		op("/project1/main_app").CallDMXPreset(29)

	if _now.hour == 23 and _now.minute == 59 and _now.second > 58:
		# - self shutdown
		op("/project1/main_app").Shutdown()

	if len(_preschedule.keys()) > 0:
		# -- scheduled:
		dtstr: str = "{:%H:%M}".format(_now)
		if dtstr in _preschedule and _now.second < 3:
			# TODO: random pick or another method
			debug("Found scheduled, ", _preschedule[dtstr])
			op("/project1/main_app").UpdateRootFolder(_preschedule[dtstr])
	else:
		# -- ad-hoc, TODO:
		if _now.minute == 40 and _now.second < 3:
			op("/project1/main_app").ReloadPipelineConfig(now = _now)

		if _now.minute == 45 and _now.second < 3:
			# TODO: timing
			op("/project1/main_app").RunPipeline(_now)

		# if _now.minute == 27 and _now.second < 3:
		#	op("/project1/main_app").UpdateRootFolder(-1)

	return