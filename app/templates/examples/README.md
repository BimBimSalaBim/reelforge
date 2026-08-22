# Worked examples

The storyboard shown to the model when it writes a new one. Each template in
`app/templates/__init__.py` names one of these by its `example=` field.

These are application assets, not reel output: they are read as **text** and
pasted into the prompt, never imported or executed. A template without a usable
example produces markedly worse code, which is why they live here rather than
being fetched from a reel's own directory.

To add one, drop a `<name>.py` in beside these and set `example="<name>"` on the
template.
