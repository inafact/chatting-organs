//
/* TODO: modular */
//
Server.killAll;

ServerOptions.devices.do({| dev |
	dev.postln;
});

(
// Server.default.options.device = "ASIO : MOTU Gen 5";
// Server.default.options.device = "ASIO : Komplete Audio 6";
Server.default.options.device = "ASIO : Roland Rubix";
Server.default.options.numOutputBusChannels = 4;
Server.default.options.sampleRate = 48000;
Server.local.boot.makeGui;
NdefMixer(Server.local);
)

/*
Ndef(\test1, { SinOsc.ar(120) });
Ndef(\test2, { SinOsc.ar(240) });
Ndef(\test3, { SinOsc.ar(80) });
*/

(
//
Spec.add(\bufnum, ControlSpec(0, 50, \lin, 1, 0));
Spec.add(\busindex, ControlSpec(0, 511, step: 1));
Spec.add(\ioindex, ControlSpec(0, Server.default.options.numInputBusChannels - 1, step: 1));
Spec.add(\pps, ControlSpec(0, 60, \lin));
Spec.add(\loopgate, ControlSpec(-10, 10, \lin));
Spec.add(\loop, ControlSpec(0, 1, step: 1));
Spec.add(\startPos, \unipolar);
Spec.add(\endPos, \unipolar);
Spec.add(\widerate, ControlSpec(-100, 100, \lin));
Spec.add(\prescale, ControlSpec(0, 50, \lin));

Server.local.waitForBoot.do({
	var createWin;

	createWin = { | wid = "audio", path = nil |
		var filer = Array();
		var dir, win, sfview, btn, lview, fn, info, sender, layout;
		var ww = 820;
		var wh = 240;

		var default_sf = Array();
		if (path.notNil, {
			filer = filer ++ SoundFile.collect(path);
		});
		dir = IdentityDictionary.new;
		win = Window(wid, Rect(0, 0, ww, wh))
		.onClose_({
			"close".postln;
			dir.do({|el|
				("free: " ++ el.at(\bufnum)).postln;
				Server.default.sendMsg("/b_free", el.at(\bufnum));
				filer.at(el.at(\index)).close;
			});
			// ("free: " ++ ObjectTable.at(\default_buf).bufnum).postln;
			// Server.default.sendMsg("/b_free", ObjectTable.at(\default_buf).bufnum);
		})
		.front;
		win.addFlowLayout;

		//
		sfview = SoundFileView(win, 500@wh)
		.mouseUpAction_({|self|
			self.selections[self.currentSelection].postln;
			// if(dir.at(self.soundfile.path.asSymbol).at(\buffered) == 1, {
			// 	">>" ++ dir.at(self.soundfile.path.asSymbol).at(\bufnum).postln;
			// });
		});

		//
		fn = {|target, toggle|
			var bn = nil;
			var sf = nil;
			dir.at(target.asSymbol).put(\buffered, toggle);
			if(dir.at(target.asSymbol).at(\buffered) == 1, {
				sf = filer.at(dir.at(target.asSymbol).at(\index));
				sf.postln;
				sf.openRead(sf.path);
				dir.at(target.asSymbol).put(\bufnum, sf.asBuffer(Server.local).bufnum);
				dir.at(target.asSymbol).postln;
			}, {
				"to free".postln;
				dir.at(target.asSymbol).postln;
			});
		};

		filer.do({|el, i|
			dir.put(el.path.asSymbol, (index:i, buffered: 0));
			fn.value(el.path, 1);
		});

		if (filer.size > 0, {
			sfview.soundfile = filer.at(0);
			sfview.read(0, filer.at(0).numFrames);
		}, {
			"no files".postln;
		});

		lview = ListView(win, 300@wh)
		.items_(filer.collect({ |el| el.path }))
		.selectionMode_(\extended)
		.action_({|index|
			filer.collect({|el| el.path}).at(index.value).postln;
			sfview.soundfile = filer.at(index.value);
			sfview.read(0, filer.at(index.value).numFrames);
			sfview.refresh;
		});
	};

	createWin.value("/sound", Document.current.dir ++ "/_audio/*");
	createWin.value("/voice");

	// Ndef(\drone, { | rate = 0.5, loop = 0, pan = -1, amp = 0.5 |
	// 	Pan2.ar(PlayBuf.ar(1, ObjectTable.at(\mono_drone).bufnum, rate, loop: loop) * amp, pan);
	// });
	// Ndef(\catapult, { | rate = 0.5, loop = 0, pan = 1, amp = 0.5 |
	// 	Pan2.ar(PlayBuf.ar(1, ObjectTable.at(\mono_catapult).bufnum, rate, loop: loop) * amp, pan);
	// });

	Ndef(\bufrd1).ar(2);
	Ndef(\bufrd1, { |amp = 0.5, bufnum = 0, rate = 1, loop = 1, startPos = 0, endPos = 1, gain = 1, preamp = 1, baseFreq = 100 |
		var bo, po, freq, hasFreq;
		bo = BufRd.ar(
			2, bufnum,
            Phasor.ar(0, BufRateScale.kr(bufnum) * rate, BufFrames.kr(bufnum) * startPos, BufFrames.kr(bufnum) * endPos),
            loop, 4
        );
		// # freq, hasFreq = Pitch.kr(bo, ampThreshold: 0.02, median: 1);
		// po = PitchShift.ar(bo, 0.1, (baseFreq / freq), 0.0, 0.0);
		// Pan2.ar(po * amp * VarLag.kr(preamp, 0.5) * gain, pan);
		bo * amp * VarLag.kr(preamp, 0.5) * gain;
    });

	Ndef(\bufrd2).ar(2);
	Ndef(\bufrd2, { |amp = 0.5, bufnum = 0, rate = 1, loop = 1, startPos = 0, endPos = 1, gain = 1, preamp = 1, baseFreq = 100 |
		var bo, po, freq, hasFreq;
		bo = BufRd.ar(
			2, bufnum,
            Phasor.ar(0, BufRateScale.kr(bufnum) * rate, BufFrames.kr(bufnum) * startPos, BufFrames.kr(bufnum) * endPos),
            loop, 4
        );
		// # freq, hasFreq = Pitch.kr(bo, ampThreshold: 0.02, median: 1);
		// po = PitchShift.ar(bo, 0.1, (baseFreq / freq), 0.0, 0.0);
		// Pan2.ar(po * amp * VarLag.kr(preamp, 0.5) * gain, pan);
		bo * amp * VarLag.kr(preamp, 0.5) * gain;
    });
});

ObjectTable.put(\lastq, 0);

OSCdef(\r1, {
	|msg, time, addr, recvPort|
	var targetPrev, targetNext, st, bnum, fd = 0, targetAmp = 1;

	"/sound".post; msg.postln;

	if (ObjectTable.at(\lastq) % 2 == 0, {
		targetPrev = "bufrd1";
		targetNext = "bufrd2";
	}, {
		targetPrev = "bufrd2";
		targetNext = "bufrd1";
	});

	st = msg[1].asString.split($ );
	st.postln;

	Ndef(targetPrev.asSymbol).fadeTime = 0;
	Ndef(targetNext.asSymbol).fadeTime = 0;

	if (st.at(0).asInteger > 21, {
		bnum = -1;
		targetAmp = 0;
	}, {
		bnum = (st.at(0).asInteger - 1).clip(0, 100);
	});

	"bnum ".post; bnum.postln;

	if (st.size > 1, {
		fd = st.at(1).asInteger;
		// Ndef(targetPrev.asSymbol).fadeTime = 4;
		// Ndef(targetNext.asSymbol).fadeTime = 4;

		if (fd == 1, {
			Ndef(targetPrev.asSymbol).fadeTime = 4;
			Ndef(targetNext.asSymbol).fadeTime = 4;
		});
		if (fd == 2, {
			Ndef(targetPrev.asSymbol).fadeTime = 4;
			Ndef(targetNext.asSymbol).fadeTime = 4;
		});
		if (fd == 3, {
			Ndef(targetPrev.asSymbol).fadeTime = 4;
			Ndef(targetNext.asSymbol).fadeTime = 4;
		});
	});

	Ndef(targetPrev.asSymbol).xset(\amp, 0);
	if (bnum > -1, {
		Ndef(targetNext.asSymbol).set(\bufnum, bnum);
	});
	Ndef(targetNext.asSymbol).xset(\amp, targetAmp);

	ObjectTable.put(\lastq, ObjectTable.at(\lastq) + 1);
}, '/sound', nil, 12200);

OSCdef(\r2, {
	|msg, time, addr, recvPort|
	"/voice".post; msg.postln;
	'/voice', nil, 12200);
);

OSCdef(\init_player, {
	|msg, time, addr, recvPort|
	Ndef(\bufrd1).set(\amp, 0);
	Ndef(\bufrd2).set(\amp, 0);
	Ndef(\bufrd1).play(2);
	Ndef(\bufrd2).play(2);
	'/init_Player', nil, 12200);
);


// ---
NetAddr("127.0.0.1", 10000).sendMsg(\reload_configs, "./app_config.toml");
NetAddr("127.0.0.1", 10000).sendMsg(\reload_configs, "./app_config_en.toml");
NetAddr("127.0.0.1", 10000).sendMsg(\reload_env);
NetAddr("127.0.0.1", 10000).sendMsg(\run_pipeline);

NetAddr("127.0.0.1", 10001).sendMsg(\scene_start, 0);
NetAddr("127.0.0.1", 10001).sendMsg(\scene_start, 1);

OSCdef(\test0, { |msg, time, addr, recvPort|
	"/catapult ".post; time.postln;
	msg.postln;
}, '/catapult', nil, 9999);

OSCdef(\test1, { |msg, time, addr, recvPort|
	"/drone ".post; time.postln;
	msg.postln;
}, '/drone', nil, 9999);


OSCdef(\test2, { |msg, time, addr, recvPort|
	"/scene_start ".post; time.postln;
	msg.postln;
}, '/scene_start', nil, 9999);


OSCdef(\test3, { |msg, time, addr, recvPort|
	"/scene_end ".post; time.postln;
	msg.postln;
}, '/scene_end', nil, 9999);
// --3