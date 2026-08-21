# shared-types

Canonical type definitions shared between the backend and frontend.

The authoritative contract is the OpenAPI schema the backend generates at
`/openapi.json`. The frontend's TypeScript types in `apps/web/lib/types.ts`
mirror the Pydantic schemas in `apps/api/app/schemas/`.

To regenerate frontend types from a running backend:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o apps/web/lib/api-schema.d.ts
```

The hand-written `types.ts` is kept deliberately: it stays readable, documents
intent, and lets the frontend model a few things more precisely than the
generated output (for example, distinguishing "not measured" from "measured
zero" at the type level).
