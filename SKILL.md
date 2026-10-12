---
name: voxsmith
description: Convert text into a narrated audio file (MP3). Use when the user asks for a spoken version of a script, self-introduction, article, or notes, or asks to add narration, voiceover, or a reading of written material. Also use when an existing generated narration must be re-voiced, made louder, or kept consistent across several files.
metadata:
  short-description: Generate narrated MP3 audio from text
---

# VoxSmith

Produce a natural-sounding MP3 from a text file, with loudness normalized so
that several files can be played back to back without a volume jump.

This is a general-purpose skill. It makes no assumptions about the subject
matter, the language, or how the audio will be used, so apply it to any text
the user wants spoken rather than treating it as being for one kind of work.

`scripts/tts.py` does the whole job: it picks a working speech engine,
synthesizes the audio, encodes it to MP3, normalizes loudness, and prints a
JSON report as evidence. Run it rather than assembling a pipeline from
`edge-tts`, `gTTS`, or `ffmpeg` by hand — the parts that are easy to get wrong
(engine fallback, clipped peaks, mismatched levels) are already handled.

## Workflow

Write each text to a UTF-8 file, then run the script:

```bash
python scripts/tts.py --input script.txt --output intro.mp3
```

For a set of files that should sound like one speaker, pass them all at once
instead of repeating the command. The first item resolves an engine, and that
engine and voice are then locked for every remaining item:

```bash
python scripts/tts.py --inputs intro.txt reasons.txt --outdir out \
    --concat interview_full.mp3 --engine piper --voice en_US-ryan-high --rate 1.05
```

`--concat` is optional; it joins the parts in `--inputs` order, so a multi-part
spoken answer can also be handed over as a single file. The batch report carries
a `consistency` block — parts more than 1.0 dB apart will be audible as a level
change.

`--engine auto` (the default) tries Edge's online neural voices, then a cached
Piper model, then Google, then the Windows built-in voice, and reports each
attempt. It never triggers Piper's first-time 150 MB download on its own; pass
`--engine piper` to accept that. Run `--list-voices` to see what is available.

### Choosing a voice

Do not audition voices by generating whole scripts. Render one short sample per
candidate and open the page it builds:

```bash
python scripts/preview_voices.py --voices en_US-ryan-high en_US-lessac-medium \
    en_GB-alan-medium --outdir previews
```

That writes one MP3 per voice plus `previews/index.html`, which has an audio
player per candidate. Audition `medium` voices before committing to a `high`
one: the download is roughly 20 MB instead of 120 MB.

For quality trade-offs, voice id syntax, and what to do when an engine fails,
read [references/engines.md](references/engines.md).

## Preparing the text

The user's wording is authoritative. Do not paraphrase, tighten, or "improve"
their sentences — reproduce them, minus anything a speech engine cannot say.

Two adjustments are worth making:

1. **Split out variants instead of forcing one text to cover both.** A script
   written as "Good morning/afternoon" becomes two files, one per greeting.
   A slash is either read aloud or dropped, and neither is what the user wants.
   Offer the variants rather than silently picking one.
2. **Spell out symbols that are read unreliably.** Write "percent" for `%`,
   "and" for `&`, "number" for `#`. The script flags these in
   `text_warnings`, but fixing the text is the real solution.

Keep numbers, units, and technical terms as written; engines read them
correctly. For titles and abbreviations, write what should be spoken
("Doctor Chen", not "Dr. Chen") when the abbreviation is ambiguous.

## Verifying the result

Read the JSON report. It is the substitute for listening to the file:

- `ok` must be `true`, and `attempts` shows why any engine was skipped.
- `loudness.mean_db` should land near the `--lufs` target, and in a batch the
  `consistency.mean_db_spread` should stay under about 1.0 dB.
- `loudness.peak_db` should sit at or below the true-peak ceiling, confirming
  no clipping.
- `loudness.duration_s` should be plausible for the word count — roughly 2.4
  words per second at `--rate 1.0`. A figure far below that means truncated
  audio, so re-run before delivering.
- `text_warnings` should be empty, unless the user asked for the text as-is.

## Delivering

Use the filename the user asked for. Show the audio inline with an absolute
path so it plays in the conversation, and link the file:

```markdown
![audio](/absolute/path/intro.mp3)

[intro.mp3](/absolute/path/intro.mp3)
```

Report the duration, engine, and voice used. If you generated variants, say
what differs between them and offer to adjust voice, accent, or pace.

For batches, report the number of parts and the `consistency.mean_db_spread`.
When `--concat` produced a joined file, link that one as the primary result and
keep the per-part files as the editable source.

Delete the temporary `.txt` scripts you created once the audio is delivered,
unless the user wants them kept as editable scripts. If the shell blocks
`Remove-Item`, delete them from Python instead, using explicit absolute paths.
