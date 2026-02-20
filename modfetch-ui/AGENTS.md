# MODFETCH-UI (Vue 3 Frontend)

Vue 3 + Element Plus frontend for mod selection and download management.

## STRUCTURE
```
modfetch-ui/
├── src/
│   ├── main.ts       # Vue entry
│   └── App.vue       # Main component (29KB - all UI)
└── package.json
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| UI components | `src/App.vue` |
| Dependencies | `package.json` |

## CONVENTIONS
- Vue 3 Composition API + `<script setup>`
- Element Plus components
- VueUse composables
- TypeScript (vue-tsc)
- Vite build

## ANTI-PATTERNS
- No ESLint/Prettier config found
- Single large component (`App.vue`)
