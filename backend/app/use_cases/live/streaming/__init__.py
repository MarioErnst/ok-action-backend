"""Real-time streaming evaluator for live sessions.

A single WebSocket per active live session, opened by the client after
the parent row exists in BD. The browser streams raw 16 kHz mono PCM
audio at the supervisor; the supervisor forwards it to Gemini Live and
emits one strike event back to the client per function call the model
emits. The composed pipeline (sibling package) still runs once at
session end on the full audio and persists the child sessions.

facial_expression is not part of this pipeline. That module is
evaluated 100% in the browser from the emotion classifier stream and
never sees Gemini.
"""
