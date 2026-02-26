"""
DAT Execute DAT

me - this DAT

dat - the changed DAT
prevDAT - a simulated DAT containing previous contents

Info contains specific details on what's changed:

	rowsChanged	- list of row indices with different contents
	rowsAdded	- list of added row name indices (in dat)
	rowsRemoved	- list of removed row name indices (in prevDAT)

	colsChanged	- list of column indices with different contents
	colsAdded	- list of added column name indices (in dat)
	colsRemoved	- list of removed column name indices (in prevDAT)

	cellsChanged 	- list of cells that have changed content

	sizeChanged	- bool, true if number of rows or columns changed

Make sure the corresponding toggle is enabled in the DAT Execute DAT.
"""

from typing import List
# import json

def onTableChange(dat: DAT, prevDAT: DAT, info: ChangedDATInfo):
	return

def mapToDMX(chan: int | list):
	dmxm: constantCHOP = op("dmxmap")
	if chan > 60:
		_idx = max(0, chan - 1)
	else:
		_idx = max(0, chan - 1)
		if op("/project1/main_app").NightMode:
			debug("NightMode active")
			_idx = _idx + 30	
	channel: Channel = dmxm.chan(_idx)
	if channel != None:
		# print(channel, channel.name, channel.index)
		for i in range(dmxm.numChans):
			_channel: Channel = dmxm.chan(i)
			if _channel != None and i != channel.index:
				dmxm.par[f"const{_channel.index}value"] = 0
		dmxm.par[f"const{channel.index}value"] = 1

def sendMessage(dat: DAT):
	oscs: oscoutDAT = op("oscout_to_external")
	oscm: oscoutDAT = op("oscout_to_sound")
	idx = dat.numRows - 1		
	keys = list(map(lambda c: c.val, dat.row(0)))
	oscm.sendOSC(f"/voice", [dat.cell(idx, "speaker"), dat.cell(idx, "audio")])
	cs: int = op("/project1/main_app").GetCurrentScene()

	for k in keys[6:]:
		msg = dat.cell(idx, k)
		if msg != None and len(str(msg)) > 0:
			if cs < 5:
				if k == "drone":
					# -- NOTE: multiple message at once
					rmsgs = str(dat.cell(idx, k))
					# debug(k, rmsgs)
					rmsgs = rmsgs.split(",")
					for rmsg in rmsgs:
						oscs.sendOSC(f"/{k}", [rmsg])
					# -- 
				if k == "catapult":
					msg = dat.cell(idx, k)
					# debug(k, msg)
					oscs.sendOSC(f"/{k}", [msg])
				if k == "lighting":
					msg = dat.cell(idx, k)
					op("/project1/main_app").CallDMXPreset(int(msg) - 1)
					# mapToDMX(int(msg))
			if k == "sound":
				oscm.sendOSC(f"/{k}", [dat.cell(idx, k)])
		
def onSizeChange(dat: DAT):
	"""
	Called when the size (rows or columns) of the DAT changes.
	
	Args:
		dat: The changed DAT
	"""
	if dat.name == "queued" and dat.numRows > 1:
		ws_ref: tableDAT = op("ws_ref")
		idx = dat.numRows - 1
		speaker = dat.cell(idx, "speaker")
		line = dat.cell(idx, "line")
		line_en = dat.cell(idx, "line_en")
		audio = dat.cell(idx, "audio")
		img = dat.cell(idx, "image")
		delay_cell = dat.cell(idx, "pause")
		delay_list = str(delay_cell).split(" ")
		
		if len(delay_list) > 1:
			delay = int(delay_list[1])
		else:
			if idx == 1:
				delay = 6000
			else:
				delay = 0	
		
		# debug("delay ", delay)

		afin1: audiofileinCHOP = op("audiofilein1")
		afin2: audiofileinCHOP = op("audiofilein2")
		# trig1: triggerCHOP = op("trig1")
		# trig2: triggerCHOP = op("trig2")
		imm: baseCOMP = op("img_manager")
		imm2: baseCOMP = op("img_manager2")
		pp1: textDAT = op("pulse1")
		pp2: textDAT = op("pulse2")

		if speaker == "<ドローン>":
			afin1.par.file = audio
			# -- delay
			pp1.run(delayMilliSeconds = delay)
			# afin1.par.cue = False
			# afin1.par.cue.pulse()
			# trig1.par.trigger.pulse()
			# --
			t_cell: Cell = ws_ref.findCell("/?speaker=drone", cols=["label"])
			if t_cell != None:
				ds: baseCOMP = op("dispatcher")
				ds_en: baseCOMP = op("dispatcher_en")
				w_cell: Cell = ws_ref.cell(t_cell.row, "ws")
				ds.par.Wstarget = w_cell				 
				ds.par.Line = line
				ds_en.par.Line = line_en
			if img:
				imm.par.Reffile = audio
		else:
			afin2.par.file = audio
			# -- delay
			# afin2.par.cue = False
			# afin2.par.cue.pulse()
			# trig2.par.trigger.pulse()
			pp2.run(delayMilliSeconds = delay)
			# --
			t_cell: Cell = ws_ref.findCell("/?speaker=catapult", cols=["label"])
			if t_cell != None:
				ds: baseCOMP = op("dispatcher2")
				ds_en: baseCOMP = op("dispatcher2_en")
				w_cell: Cell = ws_ref.cell(t_cell.row, "ws")
				ds.par.Wstarget = w_cell
				ds.par.Line = line
				ds_en.par.Line = line_en
			if img:
				imm2.par.Reffile = audio
		
		sendMessage(dat)

	return
