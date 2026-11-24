# Rewrite the narration the way the teacher talks

You get the narration of a finished tutorial video, scene by scene, as JSON. Rewrite each scene's narration the way the teacher talks in his own videos. The examples at the end are his own words, transcribed from his screencasts. Keep what each narration says, in the same order; change how it is said.

In blind tests against his real recordings, his voice clone passed for him when it said things his way, and sounded like AI when it read polished lesson prose. So write the way he talks, not the way a lesson reads.

## How he talks

- He says what he does as he does it, in the first person: "So I'm gonna import useRef right next to useState." "And over here, I'll put the box above the variable." He talks to the viewer as "you" for what they see or need: "You're gonna see something called the React SVG."
- He moves on with "So", "And", "Now" or "All right", and lets a sentence run on with "and" or "so" where it flows. Long running sentences sit next to short ones: "We don't really need this."
- His words: "gonna", "wanna", "kinda", "a little", "pretty", "really", "over here", "like this", and contractions everywhere.
- At most once in a scene, he corrects himself mid-sentence, the way people do when they talk while they work: "this is gonna allow us to— or, allow TypeScript to find the types." Never "um" or "uh".
- He gives the reason in plain words ("it's a quirk of TypeScript, so you kinda have to do that, otherwise you're gonna get lots of errors"), not as a textbook definition ("The content of the box is called current").
- He never says the same sentence, or the same sentence shape, twice in a scene, and he does not open two sentences in a row with the same word ("So ... So ..."): he mixes "So", "And", "Now", "All right" and sentences that just start.

## He enjoys this, and it shows

A narration that only states things in an even tone sounds flat, even in his voice (2026-11-15: a script first written as calm statements sounded lifeless next to one written his way). He reacts:

- Where a result lands on the page, or a prediction gets its answer, he reacts the way people do: "There it is!", "Sixty, right away.", "And it's gone. Nice." At most two such moments in a scene, never two in a row, and only where something really happens.
- He asks the question the viewer has and answers it at once: "So why doesn't it jump? Because it measured first."
- He keeps moving: a long sentence that runs on with "and" is followed by a short one, and he doesn't explain the same thing twice. Short sentences keep his pace up; a slow, even pace is what makes him sound read.
- A running sentence still carries one new thing and stays under 30 words; most of his are under 20. He never stops a sentence to define a word in the middle of it ("a promise, which is a value that stands for..."): he says the plain idea, then the name, in a short sentence of its own. A beginner who has to hold the start of a sentence through a definition loses both.

## Rewrite, do not touch up

Say each scene the way he would say it, not the original with "So" put in front. Change the sentences freely around the phrases you must keep: join two short statements into one running sentence, split a long one, move a reason next to what it explains. Lesson phrases go, his phrases come in: "Our goal is to swap in the box" becomes "So what we wanna do here is swap in the box"; "Here's the page with the box" becomes "So here's our page, and now it's got the box"; "Next, ..." becomes "And then ...". A goal stays a goal, said before the code is typed: "So what we wanna do is...", never "That's how we..." or "And that's how we...", which sounds like it is already done. A narration that reads like the original with a few words changed is not done.

## What must not change

- Every phrase in a scene's `keep` list stays in its new narration exactly as written (the same words, capitals and punctuation inside it) and in the same order. The video's clicks, typing and pauses are timed on those words, so put each one where the same thing is said.
- Technical terms stay as they are written (useRef, useState, current, JSX, setInterval), and so do the numbers and words the screen shows ("State: 0", "Clicks: 3").
- The same facts, steps and order. Add nothing the screen does not show, and leave nothing out: every sentence of the original is still said, in his way. That includes the short sentences that say what a piece of code is for or when you would use it, and the ones that name the situations ahead: they give the viewer the reason, so they stay.
- About the same length: at most a quarter more or less words than the original. The video is timed on it.
- A scene that says a mistake is a bug still says "bug".
- Only spoken sentences: no code, symbols or markdown. Commas, periods, question marks, exclamation marks and an em dash for a correction are fine. "[pause]" stays where it is.
- A short scene (a title, a section card) stays short. Its first sentence stays as it is when it is the teacher's opening line.

## Your answer

One JSON object and nothing else: `{"scenes": [{"id": "s01", "narration": "..."}]}`, one entry for every scene you were given, in the same order.
