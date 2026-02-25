"""
Extension classes enhance TouchDesigner components with python. An
extension is accessed via ext.ExtensionClassName from any operator
within the extended component. If the extension is promoted via its
Promote Extension parameter, all its attributes with capitalized names
can be accessed externally, e.g. op('yourComp').PromotedFunction().

Help: search "Extensions" in wiki
"""

from TDStoreTools import StorageManager
import TDFunctions as TDF

from datetime import datetime
from pathlib import Path
import re
import json
import tomllib

class ChattingOrgans:
	"""
	ChattingOrgans description
	"""
	def __init__(self, ownerComp):
		# The component to which this extension is attached
		self.ownerComp = ownerComp
		
		# properties
		TDF.createProperty(self, 'MyProperty', value=0, dependable=True,
						   readOnly=False)

		# attributes:
		self.currentRootFolderPath: str = ""
		self.currentSceneFilePath: str = ""
		self.pipelineLastRequested: str = ""

		self.folderList: folderDAT = op("root")
		self.sceneList: folderDAT = op("scenes")
		self.currentScene: tableDAT = op("dialogue_src")
		self.currentSceneWithHeader: tableDAT = op("dialogue_src_headered")
		self.mainTimer: timerCHOP = op("timer_main")
		self.sceneTimer: timerCHOP = op("timer_scenes")
		self.oscOut: oscoutDAT = op("oscout_to_external")
		self.oscOutPipeline: oscoutDAT = op("oscout_to_pipeline")
		self.oscOutSound: oscoutDAT = op("oscout_to_sound")
	
		# promoted
		self.AutoNext: bool = True
		self.NightMode: bool = False
		self.CurrentTempo: float = 0.5
		self.AudioReady: bool = False

		# stored items (persistent across saves and re-initialization):
		storedItems = [
			# Only 'name' is required...
			{'name': 'StoredProperty', 'default': None, 'readOnly': False,
			 						'property': True, 'dependable': True},
		]
		# Uncomment the line below to store StoredProperty. To clear stored
		# 	items, use the Storage section of the Component Editor
		
		# self.stored = StorageManager(self, ownerComp, storedItems)

		# -- TODO:
		op("camera_level").par.opacity = 0
		op("image_level*").par.opacity = 0
		self.clearCurrentScene()

	# def onDestroyTD(self):
	# 	"""
	# 	Called when the extension or component is being deleted. Use this
	# 	instead of __del__ for cleanup tasks.
	# 	"""
	# 	debug("onDestroyTD called")

	def clearCurrentScene(self):
		self.currentSceneFilePath = ""
		self.currentScene.par.file = ""
		self.currentScene.clear()

	def onInitTD(self):
		"""
		Called after the extension is fully initialized and attached to the 
		component. Use this instead of __init__ for tasks that require other
		components' extensions to be available, or that use promoted members.
		"""
		debug("0.9.9", self.currentSceneFilePath)
		op("audiodevout1").par.refresh.pulse()
		# op("videodevin1").par.refresh.ulse()
		
	def SCIsReady(self):
		# system initialize when after supercollider startup
		if not self.AudioReady:
			self.oscOutSound.sendOSC("/init_player", [])
			debug("SC is ready")
			dlInst: textDAT = op("delayInstallation")
			self.AudioReady = True
			#
			lconf: textDAT = op("local_config")
			configs: dict = tomllib.loads(lconf.text)
			if "prompt" in configs.keys():
				debug(configs["prompt"])
				self.folderList.par.rootfolder = configs["prompt"]["rootfolder"]
				self.UpdateRootFolder(-1)
			if "audiodev" in configs.keys():
				debug(configs["audiodev"])
				op("audiodevout1").par.device = configs["audiodev"]["device"]
			if "videodevin" in configs.keys():
				debug(configs["videodevin"])
				# op("videodevin1").par.device = configs["videodevin"]["device"]
				op("videodevin1").par.signalformat = configs["videodevin"]["signalformat"]
			#
			""" op("audiodevout1").par.device = "{0.0.0.00000000}.{5f94edcd-226d-471c-ae8b-5b3c1764d87e}" """
			win1: windowCOMP = op("/window1")
			win2: windowCOMP = op("/window2")
			win1.par.winopen.pulse()
			win2.par.winopen.pulse()
			dlInst.run(0, delayMilliSeconds = (5 * 1000))
	
	def ReloadAndPlay(self):
		op_afin: audiofileinCHOP = op("audiofilein1")
		op_afin2: audiofileinCHOP = op("audiofilein2")		
		op_cntr: constantCHOP = op("cntr")

		if self.currentScene.numRows == 0:
			first_scene: Cell = self.sceneList.cell(1, "path")
			if first_scene != None:
				self.currentSceneFilePath = first_scene.val
				self.currentScene.par.file = first_scene.val
			else:
				return

		# -- check scene config
		# -- default
		_cam_opacity = 1
		_imgg_opacity = 1
		_mtm_length = 0.5
		_anext = False
		
		si: Cell = self.currentSceneWithHeader.cell(1, "scene_info")
		if si != None:
			si_dict = json.loads(str(si.val))
			if "camera" in si_dict:
				_cam_opacity = int(si_dict["camera"])
			if "image" in si_dict:
				_imgg_opacity = int(si_dict["image"])
			if "tempo" in si_dict:
				_mtm_length = float(si_dict["tempo"])
			if "autonext" in si_dict:
				_anext = bool(int(si_dict["autonext"]))

		op("camera_level").par.opacity = _cam_opacity
		op("image_level*").par.opacity = _imgg_opacity
		self.mainTimer.par.length = _mtm_length
		self.CurrentTempo = _mtm_length
		self.AutoNext = _anext
		# --

		# -- TODO:
		if op("webrender1").par.url != "http://localhost:9000?speaker=drone":
			op("webrender1").par.url = "http://localhost:9000?speaker=drone"
		op("level3").par.opacity.expr = 'op("trig1")[0]'
		# --

		op_afin.par.play = True
		op_afin.par.cue = True
		op_afin2.par.play = True
		op_afin2.par.cue = True
		op_cntr.par.const0value = 0

		self.currentSceneFilePath = str(self.currentScene.par.file)
		self.mainTimer.par.play = True
		self.mainTimer.par.start.pulse()

		cs: int = self.getSceneNumberFromPath()
		# -- TODO: dark
		if cs == 5:
			self.CallDMXPreset(29)
		# --
		self.oscOut.sendOSC("/scene_start", [ cs ])
		debug(f"{cs} configs -> {_cam_opacity} | {_imgg_opacity} | {_mtm_length} | {_anext}" )

	def UpdateRootFolder(self, index: int):
		rf: folderDAT = op("root")
		sf: folderDAT = op("scenes")
		if index < 0:
			# - pick last one
			path: str = str(rf.cell(rf.numRows - 1, "path"))
		else:
			path: str = str(rf.cell(index + 1, "path"))
		
		if path != None and Path(path).exists():
			if self.currentRootFolderPath != path:
				self.currentRootFolderPath = path
				sf.par.rootfolder = path
				self.clearCurrentScene()
				debug("update", self.currentRootFolderPath)
				#
				# wdt: widgetCOMP = op("/project1/2_folders_scenes/1_dlm_root")				 
			else:
				pass
				# debug("no change")
		else:
			debug("resource not found")

	def UpdateSceneFileList(self, index: int):
		debug("UpdateSceneFileList", index)
		sf: folderDAT = op("scenes")
		path: str = str(sf.cell(index + 1, "path"))
		if path != None and Path(path).exists():
			if self.currentSceneFilePath != path:
				self.currentSceneFilePath = path
				# -- TODO:
				dt: tableDAT = op("dialogue_src")		 
				dt.par.file = path
				# --
		else:
			debug("resource not found")

	def getSceneIndexFromPath(self, path: str | None = None) -> int:
		if path == None:
			current: Cell = self.sceneList.findCell(self.currentSceneFilePath, cols=["path"])
		else:
			current: Cell = self.sceneList.findCell(self.path, cols=["path"])
		if current != None:
			return current.row
		else:
			return -1
	
	def getSceneNumberFromPath(self, path: str | None = None) -> int:
		if path == None:
			current: Cell = self.sceneList.findCell(self.currentSceneFilePath, cols=["path"])
		else:
			current: Cell = self.sceneList.findCell(self.path, cols=["path"])
		if current != None:
			p: Path = Path(current.val)
			m = re.search(r"scene_(\d+)", p.name)
			if m:
				return int(m.group(1))
			else:
				return -1
		else:
			return -1

	def GetCurrentScene(self) -> int:
		# promoted version
		return self.getSceneNumberFromPath()

	def EndScene(self):
		self.mainTimer.par.play = False
		sn: int = self.getSceneNumberFromPath()
		self.oscOut.sendOSC("/scene_end", [ sn ])
		
		if sn  == 4:
			dlDMX: textDAT = op("delayDMXPreset")
			dlDMX.run(60, delayMilliSeconds = (20 * 1000))
			# self.sceneTimer.par.play = True
			# self.sceneTimer.par.start.pulse()
			# force to next
			if self.AutoNext:
				self.sceneTimer.par.play = True
				self.sceneTimer.par.start.pulse()
		elif sn == 5:
			# force to last
			self.sceneTimer.par.play = True
			self.sceneTimer.par.start.pulse()			 
		else:
			self.CallDMXPreset(60)
			if self.AutoNext:
				self.sceneTimer.par.play = True
				self.sceneTimer.par.start.pulse()

	def NextScene(self):
		current: Cell = self.sceneList.findCell(self.currentScene.par.file, cols=["path"])
		debug(current, self.currentSceneFilePath, self.currentSceneFilePath == "")
		if current == None and self.currentSceneFilePath == "":
			self.ReloadAndPlay()
		elif current != None and current.row < self.sceneList.numRows - 1:
			self.currentSceneFilePath = self.currentScene.par.file = str(self.sceneList.cell(current.row + 1, "path"))
			self.ReloadAndPlay()
		else:
			debug("all scnenes done")
			# -- TODO:
			op("webrender1").par.url = "http://localhost:9000/credit"
			ot: levelTOP = op("level3")
			ot.par.opacity.expr = 'op("for_credit")[0]'
			self.clearCurrentScene()
			dlDMX: textDAT = op("delayDMXPreset")
			dlInst: textDAT = op("delayInstallation")
			dlDMX.run(0, delayMilliSeconds = (30 * 1000))
			dlInst.run(0, delayMilliSeconds = (30 * 1000))

	def RunPipeline(self, lastRequested: datetime | None = None):	
		if lastRequested == None:
			self.oscOutPipeline.sendOSC("/run_pipeline", [])
		else:
			# only accept each hours 
			t: str = ":".join(lastRequested.isoformat("_").split(":")[:2])
			if self.pipelineLastRequested != t:
				self.oscOutPipeline.sendOSC("/run_pipeline", [])
				self.pipelineLastRequested = t

	def ReloadPipelineConfig(self, config: str = ""):
		self.oscOutPipeline.sendOSC("/reload_pipeline", [])

	def CallDMXPreset(self, preset: int = 0):
		dmxm: constantCHOP = op("dmxmap")

		if preset > 59:
			_idx = preset
		else:
			if self.NightMode:
				debug("NightMode active", preset, preset + 30)
				_idx = preset + 30
			else:
				_idx = preset
		
		channel: Channel = dmxm.chan(_idx)
		
		if channel != None:
			for i in range(dmxm.numChans):
				_channel: Channel = dmxm.chan(i)
				if _channel != None and i != channel.index:
					dmxm.par[f"const{_channel.index}value"] = 0
		
		dmxm.par[f"const{channel.index}value"] = 1

	def InstallationView(self, onoff: bool = True):
		lv1 :layermixTOP = op("layermix1")
		lv2 :layermixTOP = op("layermix2")
		lmv1: moviefileinTOP = op("loop_drone")
		lmv2: moviefileinTOP = op("loop_catapult")

		if onoff:
			debug("installation")
			lv1.par.lay3bypass = False
			lv2.par.lay3bypass = False
			lmv1.par.play = True
			lmv2.par.play = True
			op("camera_level").par.opacity = 0
			op("image_level*").par.opacity = 0
			if self.AudioReady:
				self.oscOutSound.sendOSC("/installation", [0.0])
		else:
			debug("show")
			lv1.par.lay3bypass = True
			lv2.par.lay3bypass = True
			lmv1.par.play = False
			lmv2.par.play = False
			if self.AudioReady:
				self.oscOutSound.sendOSC("/silent", [])

