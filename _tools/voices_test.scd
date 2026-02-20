//
/* TODO: modular */
//
Server.killAll;

ServerOptions.devices.do({| dev |
	dev.postln;
});

(
// Server.default.options.device = "ASIO : MOTU Gen 5";
// Server.default.options.sampleRate = 48000;
// Server.default.options.numOutputBusChannels = 4;
// Server.default.options.numInputBusChannels = 20;
// Server.default.options.device = "ASIO : MOTU Gen 5";
// Server.default.options.device = "ASIO : Roland Rubix";
Server.default.options.numOutputBusChannels = 4;
Server.default.options.sampleRate = 48000;
Server.local.boot.makeGui;
NdefMixer(Server.local);
)


Ndef(\test1, { SinOsc.ar(120) });
Ndef(\test2, { SinOsc.ar(240) });
Ndef(\test3, { SinOsc.ar(80) });

SoundFile.collect()

(
//
/* sampler test */
//
// Server.local.boot.makeGui;

Spec.add(\bufnum, ControlSpec(0, 200, \lin, 1, 0));
Spec.add(\busindex, ControlSpec(0, 511, step: 1));
Spec.add(\ioindex, ControlSpec(0, Server.default.options.numInputBusChannels - 1, step: 1));
Spec.add(\pps, ControlSpec(0, 60, \lin));
Spec.add(\loopgate, ControlSpec(-10, 10, \lin));
Spec.add(\startPos, \unipolar);
Spec.add(\endPos, \unipolar);
Spec.add(\widerate, ControlSpec(-100, 100, \lin));
Spec.add(\prescale, ControlSpec(0, 50, \lin));

Server.local.waitForBoot.do({
    var filer = Array();
    var dir, win, sfview, btn, lview, fn, info, sender, layout;
    var ww = 1080;
    var wh = 280;

	var default_sf = Array();
	// default_sf = File.readAllString(Document.current.dir ++ "/config.json").parseJSON.at("soundfiles");

    var privateBusIndex = Server.default.options.numOutputBusChannels + Server.default.options.numInputBusChannels + 32;
    var submixIndex = privateBusIndex + 50;
	ObjectTable.put(\default_buf, Buffer.alloc(Server.local, Server.local.sampleRate * 5));
	/*
    default_sf.do({|path, pathidx|
        filer = filer ++ SoundFile.collect(path);
    });
	*/
	filer = filer ++ SoundFile.collect("C:/Users/takan/workspace/_cc_sandbox/ws/outputs/2026-02-18_151651.061123/*");
    dir = IdentityDictionary.new;
    win = Window("files", Rect(0, 0, ww, wh))
    .onClose_({
        "close".postln;
        dir.do({|el|
            ("free: " ++ el.at(\bufnum)).postln;
            Server.default.sendMsg("/b_free", el.at(\bufnum));
            filer.at(el.at(\index)).close;
        });
		("free: " ++ ObjectTable.at(\default_buf).bufnum).postln;
		Server.default.sendMsg("/b_free", ObjectTable.at(\default_buf).bufnum);
    })
    .front;
    win.addFlowLayout;

    //
    sfview = SoundFileView(win, 440@wh)
    .mouseUpAction_({|self|
        self.selections[self.currentSelection].postln;
        if(dir.at(self.soundfile.path.asSymbol).at(\buffered) == 1, {
            ">>" ++ dir.at(self.soundfile.path.asSymbol).at(\bufnum).postln;
        });

    });

    //
    fn = {|target, toggle|
        var bn = nil;
        var sf = nil;
        dir.at(target.asSymbol).put(\buffered, toggle);
        //
		///*
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
		//*/
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

    //
    lview = ListView(win, 300@wh)
    .items_(filer.collect({ |el| el.path }))
    .selectionMode_(\extended)
    .action_({|index|
        filer.collect({|el| el.path}).at(index.value).postln;
        sfview.soundfile = filer.at(index.value);
        sfview.read(0, filer.at(index.value).numFrames);
        sfview.refresh;
		ObjectTable.at(\default_buf).cueSoundFile(filer.collect({|el| el.path}).at(index.value), 0);
		/*
        btn.value = dir.at(filer.at(index.value).path.asSymbol).at('buffered');
        info.value = dir.at(filer.at(index.value).path.asSymbol);
		*/
    });

    /*
    layout = VLayoutView(win, 300@wh);
    btn = Button(layout, 300@30)
    .states_([
        ["use buffer", Color.black, Color.red],
        ["buffered", Color.red, Color.white],
    ])
    .action_({|self|
        var sf = nil;
        self.value.postln;
        fn.value(lview.items.at(lview.value), self.value);
    });
    info = EZText(layout, 300@40, "info:", {|ez| ez.postln;}, ["-"], true);
    sender = EZText(layout, 300@40, "sendTo:", {|ez|
        dir.at(lview.items.at(lview.value).asSymbol).at(\bufnum).postln;
        ObjectTable.put(\oneshot_buf, dir.at(lview.items.at(lview.value).asSymbol).at(\bufnum));
        ez.value.postln;
    }, ["-"], true);
	*/

/*
    4.do({| i |
        //
        Ndef(("r1p"++(i+1)).asSymbol, {|amp = 0.5, bufnum = 0, widerate = 1, startPos = 0, endPos = 1,  gain = 1, preamp = 1, pan = 0|
            var bo = BufRd.ar(
                1, bufnum,
                Phasor.ar(0, BufRateScale.kr(bufnum) * widerate, BufFrames.kr(bufnum) * startPos, BufFrames.kr(bufnum) * endPos),
                1, 4
            );
            Pan2.ar(bo * amp * VarLag.kr(preamp, 0.5) * gain, pan);
        });
        Ndef(("r1p"++(i+1)).asSymbol).play(privateBusIndex);
        Ndef(("r1p"++(i+1)).asSymbol).set(\bufnum, dir.at(filer.at(i).path.asSymbol).at(\bufnum), \amp, 0);
    });
*/
    ObjectTable.put(\oneshot_buf, 2);
    ObjectTable.at(\oneshot_buf);

	Ndef(\vdiskin, { | rate = 1, loop = 1, pan = 0 |
		Pan2.ar(VDiskIn.ar(1, ObjectTable.at(\default_buf).bufnum, rate, loop), pan);
	});
	Ndef(\vdiskin).play();


	Ndef(\bufrd, { |amp = 0.5, bufnum = 0, widerate = 1, startPos = 0, endPos = 1,  gain = 1, preamp = 1, pan = 0, baseFreq = 100 |
		var bo, po, freq, hasFreq;
		bo = BufRd.ar(
			1, bufnum,
            Phasor.ar(0, BufRateScale.kr(bufnum) * widerate, BufFrames.kr(bufnum) * startPos, BufFrames.kr(bufnum) * endPos),
            1, 4
        );
		# freq, hasFreq = Pitch.kr(bo, ampThreshold: 0.02, median: 1);
		po = PitchShift.ar(bo, 0.1, (baseFreq / freq), 0.0, 0.0);
        // Pan2.ar(bo * amp * VarLag.kr(preamp, 0.5) * gain, pan);
		Pan2.ar(po * amp * VarLag.kr(preamp, 0.5) * gain, pan);
    });
	Ndef(\bufrd).play();

});
);

OSCdef(\r1, {
    |msg, time, addr, recvPort|
    var target, target2;

    if (addr.ip == "192.168.50.30", { target = \r1p1; target2 = \subase1 });
    if (addr.ip == "192.168.50.31", { target = \r1p2; target2 = \subase2 });
    if (addr.ip == "192.168.50.32", { target = \r1p3; target2 = \subase3 });
    if (addr.ip == "192.168.50.33", { target = \r1p4; target2 = \subase4 });

    if (target.notNil, {
        // addr.post; msg.postln;
        if (msg[2] > 0, {
            "ananlog: ".post; (addr.ip ++ " ").post; msg.postln;

			if (Server.default.statusWatcher.hasBooted, {
				Ndef(target).set(
					//  \freq, msg[2].pow(1.1 + (msg[1] / 4096)).clip(0, 20000)
					\widerate, (msg[2].pow(1.1 + (msg[1] / 4096)) * 0.0002).clip(-100, 100)
				);
				Ndef(target).set(\amp, msg[1] / 4096);
				if (target2.notNil, { Ndef(target2).set(\amp, 0.4); });
			});
        }, {
            // addr.post; msg.postln;
            // Ndef(target).set(\freq, 50);
			if (Server.default.statusWatcher.hasBooted, {
				Ndef(target).set(\amp, 0);
				if (target2.notNil, { Ndef(target2).set(\amp, 0); });
			});
        });

    }, {
       //  "analog olphan: ".post; (addr.ip ++  " ").post; msg.postln;
    });

}, '/analog', nil, 12000);

// Sing whatever pitch you like into the microphone, but have the output conform to the key you press on your connected MIDI keyboard, like a very low-rent Autotune.
// by nonprivate April 2009
// best used with headphones
// execute one by one...

s = Server.local.boot;
b = 200;		// no. of control bus to use for pitch control
(
	SynthDef("straightenUp",
		{ |baseFreq = 100|

		var in, freq, hasFreq, out;
		in = Mix.new(SoundIn.ar([0,1]));
		# freq, hasFreq = Pitch.kr(in, ampThreshold: 0.02, median: 7);
		out = PitchShift.ar(in, 0.08, (baseFreq / freq), 0.0, 0.0);
		Out.ar(0,[out, out])
		}
	).send(s);
)

s.sendMsg("/s_new", "straightenUp", n = s.nextNodeID, 1, 0);

s.sendMsg("/n_map", n, "baseFreq", b);

(
	c = NoteOnResponder(
		{ |src,chan,note,vel|

		s.sendMsg("/c_set", b, note.midicps);

		},
		nil, // any source
		nil, // any channel
		nil, // any note
		nil // any vel
	);

)

NetAddr("127.0.0.1", 10000).sendMsg(\reload_configs);
NetAddr("127.0.0.1", 10000).sendMsg(\reload_env);
NetAddr("127.0.0.1", 10000).sendMsg(\run_pipeline);


NetAddr("127.0.0.1", 10000).sendMsg(\reload_configs);
NetAddr("127.0.0.1", 10000).sendMsg(\reload_env);
NetAddr("127.0.0.1", 10000).sendMsg(\run_pipeline);
