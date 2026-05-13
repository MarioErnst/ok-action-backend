"""Per-frame evaluation pipeline for live sessions.

The composed pipeline (sibling package) runs once at session end on the
full audio. This streaming pipeline runs many times during a session on
short overlapping fragments (5 to 8 seconds) so the client can feed a
strike counter in close-to-real-time. Prompts and schemas are smaller
and faster than the composed ones: no feedback strings, looser audio
gate, integer scores plus a list of detected events per module.

facial_expression is not part of this pipeline — that module is
evaluated 100% in the browser from the emotion classifier stream and
never sees Gemini.
"""
