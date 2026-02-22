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

from pathlib import Path
import re
import json

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

		self.folderList: folderDAT = op("root")
		self.sceneList: folderDAT = op("scenes")
		self.currentScene: tableDAT = op("dialogue_src")
		self.currentSceneWithHeader: tableDAT = op("dialogue_src_headered")
		self.mainTimer: timerCHOP = op("timer_main")
		self.sceneTimer: timerCHOP = op("timer_scenes")
		# -- TODO:
		self.oscOut: oscoutDAT = op("oscout_to_external")
		self.oscOutPipeline: oscoutDAT = op("oscout_to_pipeline")
	
		self.AutoNext: bool = True
		self.NightMode: bool = False
		self.CurrentTempo: float = 0.5

		# stored items (persistent across saves and re-initialization):
		storedItems = [
			# Only 'name' is required...
			{'name': 'StoredProperty', 'default': None, 'readOnly': False,
			 						'property': True, 'dependable': True},
		]
		# Uncomment the line below to store StoredProperty. To clear stored
		# 	items, use the Storage section of the Component Editor
		
		# self.stored = StorageManager(self, ownerComp, storedItems)

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
		# TODO:
		self.clearCurrentScene()
		# self.InstallationView(True)
		op("camera_level").par.opacity = 0
		op("image_level*").par.opacity = 0
		debug("0.9.9", self.currentSceneFilePath)

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

		# -- check scene config, TODO:
		si: Cell = self.currentSceneWithHeader.cell(1, "scene_info")
		if si != None:
			si_dict = json.loads(str(si.val))
			if "camera" in si_dict:
				op("camera_level").par.opacity = int(si_dict["camera"])
			if "image" in si_dict:
				op("image_level*").par.opacity = int(si_dict["image"])
			if "tempo" in si_dict:
				self.mainTimer.par.length = float(si_dict["tempo"])
				self.CurrentTempo = float(si_dict["tempo"])
			if "autonext" in si_dict:
				self.AutoNext = bool(int(si_dict["autonext"]))
		else:
			# -- default, TODO:
			op("camera_level").par.opacity = 1
			op("image_level*").par.opacity = 1
			self.mainTimer.par.length = 0.5
			self.AutoNext = False
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

		self.oscOut.sendOSC("/scene_start", [ self.getSceneNumberFromPath() ])

	def UpdateRootFolder(self, index: int):
		rf: folderDAT = op("root")
		sf: folderDAT = op("scenes")
		path: str = str(rf.cell(index + 1, "path"))
		
		if path != None and Path(path).exists():
			self.currentRootFolderPath = path
			sf.par.rootfolder = path
			self.clearCurrentScene()
		else:
			debug("resource not found")

	def UpdateSceneFileList(self, index: int):
		debug("updatescenefilelist", index)
		sf: folderDAT = op("scenes")
		path: str = str(sf.cell(index + 1, "path"))
		if path != None and Path(path).exists():
			if self.currentSceneFilePath != path:
				self.currentSceneFilePath = path
				# -- TODO:
				dt: tableDAT = op("dialogue_src")		 
				dt.par.file = path
				# self.ReloadAndPlay()
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
		debug("snum", sn)
		self.oscOut.sendOSC("/scene_end", [ sn ])
		
		if sn  == 4:
			dlDMX: textDAT = op("delayDMXPreset_dark")
			dlDMX.run(29, delayMilliSeconds = (20 * 1000))
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
			# -- TODO:
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
			dlDMX: textDAT = op("delayDMXPreset_exhibit")
			self.clearCurrentScene()
			dlDMX.run(0, delayMilliSeconds = (30 * 1000))
			# --
	def RunPipeline(self):
		self.oscOutPipeline.sendOSC("/run_pipeline", [])

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
		else:
			debug("show")
			lv1.par.lay3bypass = True
			lv2.par.lay3bypass = True
			lmv1.par.play = False
			lmv2.par.play = False

