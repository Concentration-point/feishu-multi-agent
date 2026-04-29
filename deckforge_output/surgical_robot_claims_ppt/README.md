# Surgical Robot Claims PPT Regression

Source PDF:
`Technological origination and evolution analysis by combining patent claims and citations: A case of surgical robot domain`

## SOP Regression

This is a real-task regression for `PPT-GENERATION-SOP.md` and `ppt_project_template/`.

## Output

```text
output/surgical_robot_claims_presentation.pptx
```

## Deck Storyboard

1. Title — paper and topic
2. Agenda — 8–10 minute report route
3. Motivation — why analyze technological origins, not only trends
4. Framework — claims + citations pipeline
5. TI — claim-level technological inheritance
6. TEP / RNIT / Main Path — important elements and evolution paths
7. Data — 3313 patents, 13,097 citations, TI statistics
8. Findings — time-window migration of important technical elements
9. Main paths — four surgical robot evolution paths
10. Conclusion — contributions, findings, limitations

## Validation

Command:

```bash
python deckforge_output/surgical_robot_claims_ppt/build_surgical_robot_ppt.py
python ppt_project_template/validate.py deckforge_output/surgical_robot_claims_ppt/output/surgical_robot_claims_presentation.pptx --expected-slides 10
```

Result:

```text
PPT_VALIDATE_RESULT
status: PASS
slides: 10
issues: 0
warnings: 0
```
