// !! Select your audio interface
// Server.default.options.device = "ASIO : MOTU Gen 5";
// Server.default.options.device = "ASIO : Komplete Audio 6";
Server.default.options.device = "ASIO : Roland Rubix";

Server.default.options.numOutputBusChannels = 4;
Server.default.options.sampleRate = 48000;

Spec.add(\bufnum, ControlSpec(0, 50, \lin, 1, 0));
Spec.add(\busindex, ControlSpec(0, 511, step: 1));
Spec.add(\ioindex, ControlSpec(0, Server.default.options.numInputBusChannels - 1, step: 1));
Spec.add(\pps, ControlSpec(0, 60, \lin));
Spec.add(\loopgate, ControlSpec(-10, 10, \lin));
Spec.add(\loop, ControlSpec(0, 1, step: 1));
Spec.add(\startPos, \unipolar);
Spec.add(\endPos, \unipolar);
Spec.add(\widerate, ControlSpec(-100, 100, \lin));

ObjectTable.put(\lastq, 0);
ObjectTable.put(\sndpath,
	// "C:/opt/_audio/*"
	"E:/_audio/*"
);

Tdef(\sc_ping, {
	inf.do({
		NetAddr("127.0.0.1", 10001).sendMsg(\sc_ping);
		5.wait;
	});
});

Server.local.waitForBoot({
	AppClock.sched(5, {
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

			ObjectTable.put((wid++"_files").asSymbol, filer);

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

		createWin.value("/sound", ObjectTable.at(\sndpath));

		Ndef(\bufrd1).ar(2);
		Ndef(\bufrd1, { |amp = 0.5, bufnum = 0, rate = 1, loop = 1, startPos = 0, endPos = 1, gain = 1, preamp = 1, baseFreq = 100 |
			var bo, po, freq, hasFreq;
			bo = BufRd.ar(
				2, bufnum,
				Phasor.ar(0, BufRateScale.kr(bufnum) * rate, BufFrames.kr(bufnum) * startPos, BufFrames.kr(bufnum) * endPos),
				loop, 4
			);
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
			bo * amp * VarLag.kr(preamp, 0.5) * gain;
		});

		Tdef(\sc_ping).play;
	});
});

OSCdef(\sound, {
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
		if (fd == 4, {
			Ndef(targetPrev.asSymbol).fadeTime = 0;
			Ndef(targetNext.asSymbol).fadeTime = 0;
		});
	});

	Ndef(targetPrev.asSymbol).xset(\amp, 0);
	if (bnum > -1, {
		Ndef(targetNext.asSymbol).set(\bufnum, bnum);
	});
	Ndef(targetNext.asSymbol).xset(\amp, targetAmp);

	ObjectTable.put(\lastq, ObjectTable.at(\lastq) + 1);
}, '/sound', nil, 12200);

OSCdef(\installation, {
	|msg, time, addr, recvPort|
	var bnum;

	"/installation".post; msg.postln;

	bnum = ObjectTable.at("/sound_files".asSymbol).size - 1;
	"bnum ".post; ObjectTable.at("/sound_files".asSymbol).last.path.post; bnum.postln;

	Ndef(\bufrd1).fadeTime = 2;
	Ndef(\bufrd2).fadeTime = 2;
	Ndef(\bufrd1).set(\bufnum, bnum);
	Ndef(\bufrd1).xset(\amp, msg[1].asFloat);
	Ndef(\bufrd2).xset(\amp, 0);

	ObjectTable.put(\lastq, 0);
}, '/installation', nil, 12200);

OSCdef(\voice, {
	|msg, time, addr, recvPort|
	// TODO
	"/voice".post; msg.postln;
}, '/voice', nil, 12200);

OSCdef(\init_player, {
	|msg, time, addr, recvPort|
	Ndef(\bufrd1).set(\amp, 0);
	Ndef(\bufrd2).set(\amp, 0);
	Ndef(\bufrd1).play(2);
	Ndef(\bufrd2).play(2);
}, '/init_player', nil, 12200);

OSCdef(\silent, {
	|msg, time, addr, recvPort|

	Ndef(\bufrd1).fadeTime = 2;
	Ndef(\bufrd2).fadeTime = 2;
	Ndef(\bufrd1).xset(\amp, 0);
	Ndef(\bufrd2).xset(\amp, 0);

	ObjectTable.put(\lastq, 0);
}, '/silent', nil, 12200);

Server.local.boot.makeGui;
NdefMixer(Server.local);
