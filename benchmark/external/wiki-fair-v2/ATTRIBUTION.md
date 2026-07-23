# Wiki-Fair v2 attribution and data terms

The files in this directory are deterministic transformations of the
`wiki-fair-v2-dev-no-coref` and `wiki-fair-v2-test-no-coref` benchmark files
from [`ad-freiburg/wiki-entity-linker`](https://github.com/ad-freiburg/wiki-entity-linker)
at commit `c9a3fe9c4933888d756d702fdb9ff607fc36aa26`.

The upstream repository publishes its work under Apache License 2.0; a copy is
available in this repository's root `LICENSE`. The article text originates
from English Wikipedia and remains available under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) and the
[GNU Free Documentation License](https://www.gnu.org/licenses/fdl-1.3.html).
The source article URL is retained on every transformed record. Wikidata IDs
and names are provided under [CC0](https://creativecommons.org/publicdomain/zero/1.0/).

EAT Inline changed the source material by:

- retaining only top-level labels with a Wikidata `Q` identifier;
- excluding date, quantity, NIL and nested labels;
- separating the upstream dev records into model-training records;
- separating the upstream test records into gold-free inference records and
  scorer-only records;
- generating a separate oracle-assistance file that replaces public gold spans
  with `@@EAT entity:QID@@` references for a controlled upper-bound test;
- constructing a closed candidate registry from canonical label names; and
- serialising the transformed records as deterministic JSON Lines.

The exact source and derived-file checksums are recorded in `manifest.json`.
No claim is made that this closed candidate registry represents full-Wikidata
entity linking. The oracle EAT references are derived from test labels; they
are not human-authored annotations and must not be presented as such.
