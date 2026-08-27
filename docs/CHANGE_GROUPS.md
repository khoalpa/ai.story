# Change groups

The repository may contain work from several independent areas at once. Stage and
review them in the following order instead of committing the entire worktree:

1. `audio/adapters`, `audio/services`, and their audio contract tests.
2. Audio GUI and workspace files, with their GUI contract tests.
3. `video` rendering, validation, and media-quality files with video tests.
4. Video GUI and workspace files with their GUI tests.
5. Audio BGM and video font assets with their manifests and license files.
6. Prompt and user-guide artifacts.
7. Packaging, CI, dependency, and documentation changes.

Run `git diff --check` and the verification commands in `README.md` after each
group. Binary media should be reviewed by checksum and playback, not only by Git
diff. Do not combine removal of old prompt versions with unrelated renderer code.
