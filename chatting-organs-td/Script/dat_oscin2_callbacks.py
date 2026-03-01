"""
OSC In DAT Callbacks

me - this DAT

peer - a Peer object describing the originating message
  peer.close()    #close the connection
  peer.owner  #the operator to whom the peer belongs
  peer.address    #network address associated with the peer
  peer.port       #network port associated with the peer
"""

from typing import List, Any
from os import path
from pathlib import Path

def onReceiveOSC(dat: oscinDAT, rowIndex: int, message: str, 
                 byteData: bytes, timeStamp: float, address: str, 
                 args: List[Any], peer: Peer):
	"""
	Called when an OSC message is received.
	
	Args:
		dat: The DAT that received a message
		rowIndex: The row number the message was placed into
		message: ASCII representation of the data
		byteData: Byte array of the message
		timeStamp: Arrival time component of the OSC message
		address: Address component of the OSC message
		args: List of values contained within the OSC message
		peer: Peer object describing the originating message
	"""
	# print(address, args)
	
	if address == "/sc_ping":
		op("/project1/main_app").SCIsReady()

	if address == "/pipeline_finished":
		# -- TODO:
		tf: Path = Path(str(args[-1]))
		debug(tf)
		#if path.exists(tf):
		#	op_dsc.par.file = tf
	if address == "/stop":
		op_afin: audiofileinCHOP = op("audiofilein1")
		op_afin.par.play = False
		op_afin2: audiofileinCHOP = op("audiofilein2")
		op_afin2.par.play = False
	if address == "/reload_and_play":
		op("/project1/main_app").ReloadAndPlay()
	if address == "/reload_and_play":
		op("/project1/main_app").ReloadAndPlay()
	if address == "/scene_start":
		cmd = int(args[-1])
		debug("cmd", cmd)
		if cmd == 0:
			op("/project1/main_app").InstallationView(False)
		else:
			if (cmd != op("/project1/main_app").GetCurrentScene()) and (not op("/project1/main_app").IsCurrentSceneProgress()):
				op("/project1/main_app").NextScene()
	if address == "/next_scene":
		op("/project1/main_app").NextScene()
	return
