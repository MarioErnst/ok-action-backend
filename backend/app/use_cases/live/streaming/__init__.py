"""Real-time streaming evaluator for live sessions.

A single WebSocket per active live session, opened by the client after
the parent row exists in BD. The browser streams raw 16 kHz mono PCM
audio at the supervisor; the supervisor forwards it to AssemblyAI for
literal Spanish transcription, runs each final transcript through a
filler-word matcher, and emits one strike event back to the client per
detected muletilla.

Scope today: only muletillas trigger an in-session "corten". The
composed-eval flow (sibling package `composed`) still runs once at
session end on the full audio and persists every selected child
session — including pronunciation and accentuation. facial_expression
is evaluated 100% in the browser from the emotion classifier stream
and never reaches this package.
"""
