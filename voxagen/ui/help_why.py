WHY: dict[str, str] = {
    'Exports every waiting job in order, each with its own saved settings. You see progress per job and for the whole queue. Cancel stops the current job (nothing half-written is kept) and leaves the rest waiting.':
        'Queue ten exports, go make coffee. No babysitting each one.',
    'Shown in the queue. Leave it empty to use the export folder name.':
        'In a long queue, a good name is how you find the right job.',
    'Batch jobs never overwrite files. A new numbered folder (for example “Export (2)”) keeps both; Skip leaves the existing export alone and marks the job as skipped.':
        'Run the queue again whenever you like. Old exports stay where they are.',
    'The lowest note of the chromatic. C4 is middle C on a piano.':
        'Start where your song starts. No wasted notes below the range you need.',
    'How many notes to generate, one semitone apart. 12 notes = one octave.':
        'Fewer notes, smaller files, quicker exports.',
    'The pitch every note is tuned against. Almost all music uses 440 Hz.':
        "If your project isn't at 440 Hz, match it here and everything stays in tune.",
    "How the 12 notes are spaced. 'Equal' is what pianos and DAWs use. The others sound purer in one key and worse in others.":
        "Equal works in every key. That's why nearly every song uses it.",
    "The key that Just and Pythagorean are built on. 'Edit offsets' sets your own tuning per note.":
        'Just and Pythagorean only sound pure in one key. Pick the key of your song.',
    'On: each note is moved to its exact pitch (normal). Off: samples keep their own pitch and are only placed in order.':
        'Exact pitch means it plays in tune with anything. Switch it off only if you want the raw, untuned voice.',
    '“All samples” lists every sample with its format and detected note, lets you leave samples out and preview them. “Check for problems” looks for issues that would make the chromatic sound wrong, with a fix for each.':
        'One wrong file can ruin a chromatic. Here you spot it before exporting.',
    'Each finding says what is wrong and how to fix it. “Problem” will break or silence notes; “Check” will probably sound uneven; “Note” is information only. Double-click a finding to select that sample.':
        'Re-exporting because one note clipped is no fun. Catch it here first.',
    "Shuffle and Random use a number (the seed) to decide the order. The preview and the export always use the same one. Tick 'Keep this order' to get the same order after restarting the app.":
        'Same seed, same order. Every time — so you can redo or share an export exactly.',
    'Ready-made Natural settings: Clean (default), Expressive (keeps vibrato), Smooth (softer) and Ultra (most detail, slowest).':
        'Good settings in one click. Tweak from there if you want.',
    "How strongly slow pitch drift is pulled onto the target note. 100 % = dead flat on the target. Lower values keep some of the singer's natural drift (always centred on the target).":
        '100 % is dead steady. Drop it a little and the singer comes back.',
    'Keeps the fast natural micro-variation (vibrato, jitter) of the source. It averages out to zero and has a cap. The note stays in tune.':
        'The note stays in tune and the performance still breathes.',
    'Maximum pitch deviation humanization may keep, in cents.':
        'A safety cap. Humanization never drifts far enough to sound off.',
    '100 % keeps the vocal-tract resonances of the source (same voice at any pitch). 0 % moves them with the pitch (chipmunk / giant effect).':
        'Same person on every note. No chipmunk at the top, no giant at the bottom.',
    'Blends the time-aligned original attacks back in, keeping consonant clicks and onsets crisp.':
        'Consonants keep their snap. Words stay readable.',
    'Length of each preserved attack.':
        'Short: just the click of the attack. Longer: more of the original sound.',
    'Temporal smoothing of the spectral envelope and of voiced/unvoiced transitions. Reduces flutter; too much softens articulation.':
        'Calmer held notes. Less flutter.',
    'Raises the high-band aperiodicity floor (less metallic buzz) and limits frame-to-frame envelope jumps (less warble).':
        'That metallic buzz pitch tools leave behind? This is what removes it.',
    'Consonants, breaths and silence have no pitch: this much of them comes from the untouched original instead of the resynthesis.':
        'A breath has no pitch. Forcing one onto it sounds fake — this leaves it alone.',
    'Blend between the refined output (wet) and plain resynthesis (dry). Both sit on the target pitch. Turning it never detunes anything.':
        'Softer processing, and the note never goes out of tune.',
    'Analysis resolution. Higher is more detailed and slower; it never changes the target pitch.':
        'Got time? Go higher. The detail is audible.',
    'Quality of the final conversion to the export sample rate (soxr).':
        "Bad resampling dulls the highs. Good resampling doesn't.",
    "Matches the loudness of each processed note to the original sample. Tuning won't make notes louder or quieter (at most ±12 dB).":
        'Notes come out as loud as the samples went in. Even chromatic, no surprises.',
    'Treats sung (voiced) and unsung parts such as breaths and consonants separately. Keep it on for natural consonants.':
        'This split is most of why breaths and consonants sound real.',
    "Finds the voice's pitch range by itself. Turn off only if a very low or very high voice is detected wrongly, then set the range below.":
        'Works for almost every voice. Nothing to set.',
    'The lowest pitch the voice is searched at (when the automatic range is off).':
        'For very deep voices that get read as noise or as the wrong octave.',
    'The highest pitch the voice is searched at (when the automatic range is off).':
        'For very high voices that get read an octave too low.',
    'How often the voice is measured. Bigger = faster but less detailed.':
        'Small step: follows quick pitch moves. Big step: long exports finish sooner.',
    'Quality of converting to the export sample rate.':
        'Clean top end after the rate change.',
    "Runs the LAB effect chain on every note after the export mode (Natural, Robot, Legacy or Lab): chromatic preview, export and batch jobs. Off means effects don't touch the export at all. Your sample files are never changed.":
        'What you hear in the LAB is what ends up in the files.',
    'How many samples per second. 48000 Hz is standard; you can also type your own value.':
        "Use your DAW's rate and it won't have to convert anything.",
    '16-bit is smaller and works everywhere. 24-bit and 32-bit float keep more detail for mixing.':
        'Mixing later? 24-bit or float. Just sharing? 16-bit plays everywhere.',
    'Mono is one channel (normal for voices). Stereo keeps the left/right image of stereo samples.':
        'Voices are almost always mono. Stereo only helps with stereo samples.',
    "Adds a tiny, inaudible noise so quiet parts don't get grainy when saving as 16-bit. Leave it on.":
        "Quiet tails stay smooth. You won't hear it working.",
    'The gap between notes in the full chromatic file.':
        'A little space between notes makes slicing easier.',
    'Off: each note keeps the length of its sample. On: every note gets this length.':
        'Same length on every note — slicing and sampler mapping get predictable.',
    'Pad + trim: shorter notes get silence, longer ones are cut. Pad only: never cuts anything. Time-stretch: makes the note longer or shorter without changing its pitch.':
        'Your call: never cut a note short, or keep every note exactly the same length.',
    'A short fade at the start and end of each note removes clicks.':
        'No clicks at the edges. The note itself sounds the same.',
    'Raises the volume so the loudest point reaches this level (0 dBFS = maximum).':
        'Loud enough, never distorted.',
    "Whole chromatic keeps the notes' relative volume. Each note makes every note equally loud.":
        'Natural dynamics, or every note equally loud. Pick one.',
    'Raises or lowers the whole export.':
        'One knob for the whole export. Beats fixing it later in the DAW.',
    'If the export would be too loud and distort, it is lowered just enough. You are told when this happens.':
        "A loud export can't come out distorted. It just gets turned down a bit.",
    'Removes silence at the start and end of each sample before processing. Sounds quieter than this level count as silence.':
        'Notes start right on the beat, not after a gap of silence.',
    'One WAV with every note in a row.':
        'One file, every note. Fastest way into a sampler or Slicex.',
    'Marks where each note starts, so FL Studio Slicex cuts the file into notes by itself.':
        'Slicex does the slicing for you. No placing markers by hand.',
    'Also saves every note as its own file in a sub-folder.':
        'Drag single notes into any sampler.',
    'The folder where the export folder is created.':
        'Exports stop ending up all over the disk.',
    'Name of the new folder for this export. Existing files are never replaced without asking.':
        'Every export gets its own folder. Versions never mix.',
    'Name of the full chromatic file.':
        'Future you will know what this file is.',
    'Sub-folder and name pattern for the single notes. You can use {index} {note} {pitch} {octave} {midi} {sample} {hz}.':
        'Files named by note, so samplers can map them on their own.',
    'The sample you are experimenting with.':
        'One sample renders fast. Try ideas here, export later.',
    'The note the sample is tuned to. Try a note far from the original to hear the tools work harder.':
        'Far notes make each tool easy to hear.',
    'Renders the sample again every time you change a tool. You always hear the current settings. On a slow computer, turn it off and press Render yourself.':
        'Change something, hear it. No extra clicks.',
    "When this is on, the chain below runs after the export mode (Natural, Robot, Legacy or Lab) in the chromatic preview, the export and the batch queue. When it's off, exports sound exactly as they would without effects. The A/B player below plays the chain either way.":
        'Same effects as the LAB, now on the whole chromatic.',
    "Formant Shift moves the resonances of the vocal tract and leaves the note alone. Positive values sound smaller and younger (cartoon, chipmunk); negative ones bigger and deeper (giant, monster). The chromatic stays in tune. It runs a voice analysis, so it's slower than the other effects. ±2-4 semitones still sounds natural.":
        "Younger, older, bigger, smaller. The pitch doesn't move.",
    'Resonance shift in semitones. + = smaller/brighter voice, - = bigger/darker voice. 0 = no change.':
        'A little: subtle. A lot: cartoon or monster.',
    'Light or dark defaults for every colour you have not changed. Switching it resets the colours to that base; your font and size settings stay.':
        'Change one colour and the rest still match.',
    'Main buttons (like Export), sliders, progress bars and the original (A) waveform.':
        'The colour you see most. It sets the mood.',
    'The processed (B) sound in previews, and secondary badges.':
        'Before and after get different colours. Easy to tell apart.',
    'Outlines of the selected tab, choice, field or menu entry, and keyboard focus.':
        'You always know where you are, even with the keyboard.',
    'Behind everything: the sidebar, the dotted area and input fields.':
        'A quiet background keeps your eyes on the content.',
    'The large rounded panel that holds each page, and the folder tabs.':
        'The page stands apart from the background.',
    'The rounded cards inside the panel, and the sidebar buttons.':
        'Related settings stay grouped together.',
    'Normal buttons and controls. Hover and border shades are derived from it.':
        'Buttons that match the theme. The app feels like one thing.',
    'All text. Lighter and fainter text shades are derived from it.':
        'If a colour makes text hard to read, Voxa GEN fixes it.',
    'Recolours the Voxa GEN logo. Leave it empty for the original colours.':
        'Your colours. Your brand, your taste.',
    'Any font installed on this computer. Inter is the default; simple sans-serif fonts are the easiest to read.':
        'Long sessions are easier with a font you like reading.',
    'Makes every text bigger or smaller (85-135 %). Layouts adapt; very large text may need a bigger window.':
        'Bigger is easier on the eyes. Smaller fits more.',
    '0 % gives square corners, 100 % is the design, 150 % is extra round.':
        'Square, round, very round. Whatever looks right to you.',
    'The room inside buttons, fields and cards. Compact fits more on small screens.':
        'Compact for small screens. Roomy for easier clicking.',
    "Hand-drawn uses the design's artwork in the sidebar; the line styles use simple icons everywhere.":
        'Pick whichever helps you find pages faster.',
    'The language of every text in Voxa GEN: buttons, explanations, help and notifications. It changes right away; nothing restarts and no work is lost.':
        'Every setting is easier to get in your own language.',
    'Themes, colours, font, text size and roundness live on the Appearance page.':
        'Colours, font, size — all in one page.',
    'Short fades when you change page or tab. Turn off if you prefer instant changes.':
        'Fades show what changed. Off feels instant.',
    'Hides the logo and the page names to leave more room for the content.':
        'More room for the work. Handy on laptops.',
    'Small confirmations such as “Preset saved” or “Pitch analysed”.':
        'A quick "that worked" that doesn\'t get in the way.',
    'Useful when Voxa GEN is behind other windows during a long export.':
        "You'll notice the export finished even from another window.",
    'Prevents cancelling a long export by accident.':
        "One stray click won't throw away a 20-minute export.",
    "Where exports go when the Generator's “Save in” field is empty.":
        'Stop picking a folder every time.',
    'Only changes how loud previews play. Exports are not affected.':
        "Previews at a comfortable level. Exported files don't change.",
    'Re-render previews when you change a setting. Turn off on slow computers and use the Render button instead.':
        'Previews always match the settings. Slow PC? Turn it off.',
    'Start previews with looping switched on.':
        'Hearing it a few times in a row makes it easier to judge.',
    "Processed notes are kept on disk so previews and exports don't redo the same work. Clearing frees space; nothing else changes.":
        'Work already done gets reused. Previews and exports get much faster.',
    'Distortion drives the voice into a clipper. New harmonics pile up, and loud parts get dirtier than quiet ones: angry, broken, a blown-out speaker. Villains and screams live here. Drive is how hard it hits, Type the kind of clipping, Tone takes the edge off the top. Start at 12-18 dB of drive with 30-50 % mix.':
        'Angry, aggressive, broken. Cuts through a busy mix.',
    'How hard the voice hits the clipper. More drive = more grit and sustain.':
        'More drive, more grit. Less keeps the voice recognisable.',
    'Soft rounds the peaks, Hard cuts them flat, Wavefold folds them back (metallic), Fuzz is asymmetric and buzzy.':
        'Warm to metallic. Each type has its own flavour.',
    'Low-pass after the clipper. Lower values remove fizz and make the sound darker.':
        'Takes the fizz off and keeps the drive.',
    'Level after the effect, to keep loudness under control.':
        'Stops the effect from making things suddenly louder.',
    "Saturation rounds off the peaks and adds a few low harmonics. Fuller, warmer, still clean. That's what sets it apart from Distortion. The level is matched to the input, so it won't just get louder. Good for a thin sample or an old-record feel. Character picks tape (smooth top) or tube (even harmonics); Warmth adds asymmetry. 6-10 dB of drive stays subtle.":
        'Thin voice? This makes it fuller and warmer — without sounding distorted.',
    'How much the voice is pushed into the soft curve.':
        'A little warms it up. A lot colours it on purpose.',
    'Tape is smooth and slightly darker; Tube adds even harmonics for a richer sound.':
        'Tape is smooth. Tube is richer.',
    'Asymmetry and darkening. Higher = warmer and rounder.':
        'Rounder and softer as you go up.',
    'Tremolo moves the volume up and down; the pitch stays put. The voice pulses, stutters or wobbles. Shaky, nervous, retro, or square waves for a chopped glitch. Rate is pulses per second, Depth how deep the dips go, Shape the curve of each pulse. 5-7 Hz at 50 % depth is the classic wobble.':
        "Shaky, nervous, rhythmic. The pitch doesn't change.",
    'Pulses per second.':
        "Set it to the song's tempo and the pulses land on the beat.",
    'How quiet the dips get. 100 % = down to silence.':
        'Low: a gentle pulse. High: the voice gets chopped.',
    'Sine is smooth, Triangle is linear, Square chops on/off.':
        'Smooth waves or hard chops.',
    'Offsets the right channel in stereo exports. The pulse then moves left and right. No effect in mono.':
        'In stereo, the pulse moves from speaker to speaker.',
    'Vibrato raises and lowers the pitch at a steady speed, the way a singer does. The average stays on the note. Expressive held notes, old cartoons, or seasick at high depth. Rate is wobbles per second, Depth how far the pitch moves in cents (100 cents = 1 semitone), Onset how long it waits to fade in. 5-6 Hz and 20-40 cents sounds natural.':
        'Held notes sound sung, not frozen. Still in tune.',
    'Wobbles per second.':
        '5 to 7 per second sounds like a real singer.',
    'Maximum pitch deviation in cents (100 = one semitone).':
        'Small sounds natural. Big sounds dramatic — or seasick.',
    'Fade-in time. The attack of the note stays steady.':
        'Real singers start steady and add vibrato after. This does the same.',
    'Sine is smooth; Triangle sweeps at constant speed.':
        'Round and natural, or a mechanical sweep.',
    "Pitch Variation lets the pitch wander around the note, randomly but smoothly, with the average still in tune. There's no steady rhythm like Vibrato has, so it comes out unsteady, drunk, ghostly, or just more human. The randomness is fixed per note: preview and export match. Depth is the largest deviation in cents, Speed how often it turns. Under 20 cents stays subtle.":
        'Kills the robot-flat sound. Notes stay in tune.',
    'Largest deviation from the note, in cents.':
        'A few cents is enough to sound human. More starts to wobble.',
    'How often the drift changes direction per second.':
        'Slow sounds natural. Fast sounds nervous.',
    'BitCrusher lowers the bit depth and the sample rate of the voice. Fewer bits bring hiss and harsh steps; a lower rate brings metallic aliasing. 8-bit, old consoles, broken radio. 8 bits at about 11 kHz is the classic console; 4 bits is wrecked.':
        'Retro, video game, lo-fi.',
    'Resolution. 16 = clean, 8 = retro, 1-4 = destroyed.':
        'Fewer bits: older and dirtier.',
    'Rate the voice is held at. Lower = more metallic aliasing.':
        'Lower rate: more digital, more metallic.',
    "Double Pitch adds a second voice a musical interval away, like singing in octaves or harmony. The original stays as it is; the copy comes in at the level you set. -12 gives a monster layer, +12 a cartoon one, +7 a power-chord feel. Detune makes the two voices beat against each other. Formants decides whether the copy keeps the original timbre or follows the pitch. It uses voice analysis, so it's slower.":
        'Octaves or harmonies without recording again.',
    'Transposition of the copy in semitones (12 = one octave).':
        'An octave always works. Fifths and thirds make a harmony.',
    'Small offset that makes the layer beat and sound thicker.':
        'A tiny detune, and it sounds like a second singer.',
    'Volume of the copy relative to the original.':
        'Keep the copy quieter. The main voice should lead.',
    'Keep = natural layer; Follow = chipmunk/giant timbre on the copy.':
        'Keep: a natural second voice. Follow: cartoon or monster.',
    'Starts the copy slightly later for a doubled feel.':
        'A short delay sounds like two separate takes.',
    'The Frequency Shifter adds the same number of hertz to every part of the sound. A pitch shift keeps the harmonics in proportion; this breaks them. The voice goes metallic, alien or bell-like, and a little out of tune. 5-30 Hz gives a phasing shimmer; 100 Hz and up sounds robotic. Positive goes up, negative goes down.':
        "Alien, robotic, unsettling. Pitch shifting can't do this.",
    'Hertz added to every component of the sound.':
        'A little makes the voice uneasy. A lot makes it unrecognisable.',
    'Chorus mixes in copies of the voice on short, slowly moving delays. Tiny pitch and timing differences make it sound like several singers, wider and softer. Dreamy, choir-like, or a ghost. Voices is how many copies, Rate and Depth how much they move, Delay how far behind they sit, Spread how wide they go in stereo.':
        'One voice, several singers. Wider and fuller.',
    'Number of copies.':
        'More copies, thicker group.',
    'How fast the copies drift.':
        'Slow drift is calmer.',
    'How much the copies drift (more = more detune).':
        'More depth, more obvious detune.',
    'Base delay of the copies.':
        'Longer delay, more like separate singers.',
    'Stereo width of the copies (stereo exports only).':
        'Spreads the copies across the stereo field.',
    'The Phaser mixes the voice with a phase-shifted copy, which cuts moving notches into the spectrum. It swooshes and swirls: underwater, spacey, psychedelic. Rate is the sweep speed, Depth how far it sweeps, Center where the notches sit, Stages how many there are, Feedback how sharply they ring.':
        'Swirling, underwater, psychedelic.',
    'Sweeps per second.':
        "Match the song's tempo for a rhythmic swoosh.",
    'Sweep range (up to ±2 octaves).':
        'Wider sweep, more drama.',
    'Middle of the sweep.':
        'Moves where the swirl sits in the voice.',
    'More stages = more notches and a stronger effect.':
        'More stages, stronger effect.',
    'Resonance of the notches.':
        'More feedback, sharper swoosh.',
    "The Ring Modulator multiplies the voice by a second tone, the carrier. The rhythm of the words survives, but the pitch turns into metallic sum and difference tones. That's the old robot voice. With the carrier following the note, the robot sounds the same across the whole chromatic; a fixed carrier gives each note its own colour. 30-60 % mix keeps the words understandable.":
        'Robotic, metallic, bell-like.',
    'Follows the note: carrier = note × ratio. Fixed: the same frequency for every note.':
        'Following the note keeps it musical on every note.',
    'Carrier frequency as a multiple of the note (when following the note).':
        "1 or 2 sound musical. Odd ratios sound strange — sometimes that's the point.",
    'Carrier frequency (when fixed).':
        'Every note gets the same robotic colour.',
    'Sine is smooth; Square and Triangle add buzz.':
        'Smooth is cleaner. Buzzy is harsher.',
    'Noise puts a noise layer under the voice. Its level is relative to the voice: quiet and loud samples get the same amount. Follow makes it rise and fall with the voice, and the gaps between notes stay clean. Radio, old tape, whispers, breathy horror. Types: white (bright hiss), pink (soft hiss), brown (rumble), crackle (vinyl).':
        'Whispery, radio, old tape.',
    'Colour of the noise.':
        'Bright hiss to dark rumble.',
    'Noise level relative to the voice. -24 dB is clearly audible but behind it.':
        'Adds texture without covering the words.',
    '100 % = noise only while the voice sounds; 0 % = constant.':
        'Silence between notes stays silent.',
    'The EQ boosts or cuts frequency ranges. Low cut clears rumble and mic noise. The low shelf adds or takes away body, the mid band handles presence and nasal tone, the high shelf adds air or darkness, and high cut removes hiss or fakes a phone or radio. Moves of 2-4 dB are usually plenty. Everything at 0 dB with the cuts at their limits changes nothing.':
        'Cleans up the voice so it sits better in the mix.',
    'Removes everything below. 20 Hz = off.':
        "Rumble out. The voice itself doesn't change.",
    'Where the low shelf starts.':
        'Decides how much of the low end you touch.',
    'Body and weight of the voice.':
        'More body is warmer. Less is lighter.',
    'Centre of the mid band.':
        'Aim it at the exact problem in the voice.',
    'Presence (2-4 kHz) or nasal tone (800 Hz-1.5 kHz).':
        'Up for presence. Down for less nasal.',
    'Higher Q = narrower band.':
        'Narrow fixes one thing and leaves the rest alone.',
    'Where the high shelf starts.':
        'Decides how much of the top end you touch.',
    'Air and brightness.':
        'More air, brighter voice.',
    'Removes everything above. 20000 Hz = off.':
        'Tames harshness and hiss.',
    'Matches the volume of each processed note to the original sample.':
        'Robot notes come out as loud as their samples. No jumps between notes.',
    'Solid cards are filled blocks; outlined cards also get a thin border, which helps on very dark or very light themes.':
        'On very dark or very light themes, a thin border keeps the cards from disappearing.',
}
