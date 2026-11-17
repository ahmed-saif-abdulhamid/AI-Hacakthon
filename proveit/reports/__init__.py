"""Report writers: every Markdown and JSON file a run produces, built from run state by code.

The pipeline decides what happens; these modules only format what was decided, so the files in
``outputs/`` read the same whichever stage wrote them. One module per phase, mirroring
``proveit.pipeline.stages``; ``common`` holds what several phases share.
"""
