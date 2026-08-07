# Tasks: issue-21-feat-content-generate-20-published-quest

- [ ] 1. Draft new questions citing existing sources in `content/sources/` or newly created source YAMLs without requiring R2 snapshot uploading.
- [ ] 2. Set status to `published` (or `draft`) ensuring all schema rules match in `content/schemas/question.schema.json`.
- [ ] 3. Vary correct option placement (A/B/C/D) across questions to pass `npm run lint:content`.
- [ ] 4. Run `npm run lint:content` and `npm run test:content` to verify content validity.
- [ ] 5. Create PR with valid questions.

## Tests

- [ ] T1. `npm run lint:content` passes with zero errors.
- [ ] T2. `npm run test:content` passes.
