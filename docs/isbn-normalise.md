# ISBN normalisation

`src/Yugong/extensions/isbn_normalise.py` is a YuGong port of the standalone
[ISBN-normaliser-forMGP](https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP)
bot.  The HTTP/login/edit-summary layers are replaced by YuGong's own page
processing; the extension only rewrites the current page.

## What it changes

| Input | Output |
|-------|--------|
| `{{ISBN|9787302511625}}` | `{{ISBN|978-7-302-51162-5}}` |
| `{{ISBNT|0306406152}}` | `{{ISBNT|0-306-40615-2}}` |
| `{{Cite book|isbn=9787302511625}}` | `{{Cite book|isbn=978-7-302-51162-5}}` |
| `[[Special:网络书源/9787302511625\|ISBN 9787302511625]]` | `{{ISBN|978-7-302-51162-5}}` |
| `[[Special:网络书源/9787302511625\|9787302511625]]` | `{{ISBNT|978-7-302-51162-5}}` (no prefix) |
| `[[Special:网络书源/9787302511625\|某书]]` | Qiuwen: `[[Special:网络书源/978-7-302-51162-5\|某书]]`; Moegirl: `{{ISBN\|978-7-302-51162-5\|某书}}` |

Invalid values are not silently discarded:

* an ISBN-shaped value with a bad check digit is hyphenated and gets a comment
  naming the expected digit (`校验位为5`), if the registration range can still
  be matched;
* an ISBN-shaped value with a valid check digit but no matching range gets a
  `组区号与出版者号无法匹配` comment;
* a `Special:BookSources` target that is not an ISBN is replaced by its visible
  display text plus a comment recording the old target.  A *valid* non-ISBN
  EAN-13 target is left alone, because it is a legitimate barcode lookup.

Only valid ISBNs are rewritten.  Bare ISBN text in prose is **not** wrapped in
`{{ISBN}}`.

## Template conventions differ

Do not assume the Moegirl semantics apply to Qiuwen.  `isbn_template_style`
selects the convention:

### `qiuwen` (default)

`{{ISBN|isbn1|isbn2|…|isbn9}}` — parameters 1–9 are all ISBNs.  Named options
are `plainlink=`, `leadout=` and `invalid1=`…`invalid9=`.  `{{ISBNT}}` is the
same template with `plainlink`.  Parameter 2 is **not** a display label, so the
extension normalises every positional ISBN and never merges two ISBNs into
`{{ISBNT}}`.

Because `{{ISBN}}` has no display-text parameter, a BookSources link with a
custom label cannot be converted faithfully.  The extension keeps the link and
normalises only its ISBN target instead.

Default template names: `ISBN`, `ISBNT`, `Cite book`, `Citation`.

### `moegirl`

`{{ISBN|isbn|display text}}` — parameter 1 is the ISBN and parameter 2 replaces
the default display text.  `{{ISBNT|isbn}}` is the no-prefix variant.  The
extension normalises parameter 1, hyphenates ISBN runs inside the display text,
and (with `isbn_rehyphenate_equal_label = true`) collapses a template whose
parameters 1 and 2 are the same ISBN into `{{ISBNT|isbn}}`.  The merge respects
`overwrite_template_name`.

Default template names: `ISBN`, `ISBNT`, `Cite book`.

## Settings

```toml
enable_isbn_normalise = false
isbn_template_style = "qiuwen"        # or "moegirl"
isbn_convert_10_to_13 = false
isbn_rehyphenate_equal_label = false  # moegirl style only
isbn_template_names = []              # empty = style defaults
isbn_range_message_path = ""          # empty = bundled RangeMessage.xml
```

The bundled range file is `src/Yugong/resources/RangeMessage.xml`, published by the
International ISBN Agency.  Replacing it takes effect without restarting: the
loader keys its cache on the file's mtime and size.  A missing or malformed file
raises instead of silently disabling the job.  New registration groups are
allocated over time; refresh the file from
<https://www.isbn-international.org/export_rangemessage.xml> when convenient.

## Deliberate limits

* The job does not invent a display label or reflow text around a removed
  BookSources link.
* `Cite book` and `Citation` are only touched through their `isbn=` parameter;
  their positional parameters are normalised only when the value is a valid
  ISBN, so author/title positions are safe.
* The HTML comments added for bad values are wikitext comments: MediaWiki strips
  them before template expansion, so they do not affect the rendered page.
