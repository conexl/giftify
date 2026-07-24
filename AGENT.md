# AGENTS.md

## Project Overview

This project is a web dashboard for automatically purchasing Telegram gifts based on user-defined rules.

Users create purchase rules such as:

* Buy gifts from selected collections.
* Buy only when the price is less than or equal to a specified value.
* Limit purchases by daily budget.
* Limit the number of purchases.
* Filter gifts by model, backdrop, symbol, rarity, or gift number.

The main dashboard consists of two primary sections:

* Left side: purchase rule management.
* Right side: gifts already purchased by the bot.

The product should feel reliable, fast, minimal, and professional. Avoid excessive crypto aesthetics, cyberpunk visuals, neon effects, and unnecessary decoration.

---

## Primary Product Goal

The main user flow should be extremely simple:

1. Open the dashboard.
2. Create a purchase rule.
3. Select one or more gift collections.
4. Set a maximum purchase price.
5. Configure spending limits.
6. Enable the rule.
7. Monitor purchased gifts in real time.

A user should be able to create and activate a basic rule in less than one minute.

---

## Assumed Tech Stack

Unless the repository already uses another stack, use:

* Next.js
* React
* TypeScript
* Tailwind CSS
* shadcn/ui
* Lucide icons
* Zustand for local client state
* TanStack Query for server state
* React Hook Form
* Zod for validation

Do not replace an existing project stack without a strong reason.

Before implementing anything, inspect:

* `package.json`
* existing routes
* shared components
* styling conventions
* API clients
* state management
* linting and formatting configuration

Reuse existing patterns whenever possible.

---

## Language

The initial product interface should be written in Russian.

Code, variable names, component names, comments, database fields, and API contracts should be written in English.

Examples:

```ts
const purchaseRule = {};
const dailyBudget = 500;
const isBotActive = true;
```

UI labels:

```text
Добавить правило
Максимальная цена
Купленные подарки
Приостановить автопокупку
```

Do not mix Russian and English inside the user interface unless the English term is commonly used, such as:

* TON
* Telegram
* NFT
* Floor price

Prefer Russian equivalents when they remain clear.

---

## Dashboard Layout

The main dashboard should use a two-column layout.

### Left Column

Purpose: purchase rule management.

Recommended width:

```text
380–440 px
```

The column should contain:

* Section title.
* Add rule button.
* Rule cards.
* Rule status.
* Drag-and-drop priority ordering.
* Empty state.
* Loading state.
* Error state.

The left column may remain fixed or sticky while the gift list scrolls.

### Right Column

Purpose: display gifts purchased by the bot.

The section should contain:

* Section title.
* Gift count.
* Search.
* Filters.
* Sorting.
* Card/table view switch.
* Purchased gift grid or table.
* Empty state.
* Loading skeletons.
* Pagination or infinite scroll.

The right column should use all remaining available width.

### Responsive Behaviour

Desktop is the primary target.

For smaller screens:

* Stack the sections vertically.
* Show purchase rules first.
* Preserve all primary actions.
* Avoid horizontal scrolling where possible.
* Convert dense tables into cards.

Do not attempt to fit the desktop two-column layout on narrow mobile screens.

---

## Top Navigation

The top navigation should display:

* Product logo and name.
* Available balance.
* Amount spent today.
* Daily spending limit.
* Bot status.
* Notifications.
* User profile.
* Emergency stop button.

Example:

```text
Баланс: 2 450 TON
Потрачено сегодня: 340 / 500 TON
Бот активен
```

The emergency stop action must be clearly visible.

Button label:

```text
Приостановить автопокупку
```

When the bot is paused:

```text
Возобновить автопокупку
```

The emergency stop button must require confirmation when active purchases may be affected.

---

## Purchase Rules

Each purchase rule should be represented as a compact card.

A rule card should display:

* Rule name.
* Active or paused state.
* Selected collections.
* Price condition.
* Optional attribute filters.
* Daily budget.
* Purchase count.
* Priority.
* Last triggered time.
* Context menu.
* Enable/disable switch.

Example:

```text
Plush Pepes

Коллекция: Plush Pepes
Цена: ≤ 100 TON
Фон: Blue, Black
Покупок сегодня: 3 / 10
Статус: Активно
```

### Rule States

Support at least:

* Active.
* Paused.
* Disabled.
* Budget reached.
* Insufficient balance.
* Connection error.
* Validation error.

Use text and icons in addition to color.

Do not represent status only with a colored dot.

### Rule Actions

Each rule should support:

* Edit.
* Duplicate.
* Pause.
* Resume.
* Delete.
* Move priority.
* View matching purchases.

Deleting a rule must require confirmation.

Pausing should not delete or reset rule configuration.

---

## Create and Edit Rule Flow

Open rule creation in a side panel or modal.

Prefer a side panel on desktop because it allows the user to keep dashboard context visible.

The form should be divided into understandable sections.

### Section 1: Basic Information

Fields:

* Rule name.
* Rule description, optional.
* Enabled state.

If no name is provided, generate one from the selected collection and price condition.

Example:

```text
Plush Pepes до 100 TON
```

### Section 2: Gift Selection

Fields:

* Collections.
* Models.
* Backdrops.
* Symbols or patterns.
* Rarity percentage.
* Gift number range.
* Upgraded gifts only.
* Excluded attributes.

Collection selection must support:

* Search.
* Multiple selection.
* Clear selected values.
* Visible selected chips.
* Keyboard navigation.

### Section 3: Price Conditions

The MVP must support:

```text
Purchase price ≤ maximum price
```

Field:

```text
Максимальная цена: [100] TON
```

Later-compatible condition types may include:

* Fixed maximum price.
* Percentage below collection floor.
* Percentage below median sale price.
* Price range.
* Maximum total price including fees.

Design data models so additional condition types can be added without rebuilding the entire form.

### Section 4: Limits

Support:

* Maximum purchases per day.
* Maximum spending per day.
* Maximum number of identical gifts.
* Cooldown between purchases.
* Total rule budget.
* Maximum purchases per hour.

Fields must explain what happens after a limit is reached.

Example:

```text
После достижения лимита правило будет приостановлено до следующего дня.
```

### Section 5: Review

Before saving, show a human-readable summary:

```text
Бот будет покупать подарки из коллекции Plush Pepes
по цене не выше 100 TON.

Максимум 10 покупок в день.
Дневной бюджет — 500 TON.
```

The summary must update as the user changes the form.

### Validation

Use schema-based validation.

Validate:

* Price must be greater than zero.
* Minimum price cannot exceed maximum price.
* Daily budget cannot be below maximum single purchase price unless intentionally allowed.
* Purchase count must be a positive integer.
* At least one collection or gift filter must be selected.
* Cooldown cannot be negative.

Show validation messages next to the relevant field.

Do not rely only on toast notifications for form errors.

---

## Global Purchase Limits

Global limits must be separate from individual rule limits.

Support:

* Global daily budget.
* Global hourly budget.
* Maximum number of purchases per day.
* Minimum remaining account balance.
* Emergency stop.
* Optional confirmation threshold for expensive purchases.

Global limits always override rule-level limits.

Example:

```text
Rule budget: 500 TON
Global remaining budget: 80 TON
Result: the bot cannot spend more than 80 TON
```

The interface should explain why a matching gift was skipped.

---

## Purchased Gifts

Purchased gifts should be shown in a responsive grid by default.

Each gift card should contain:

* Gift image.
* Collection name.
* Model.
* Gift number.
* Purchase price.
* Current floor price.
* Estimated profit or loss.
* Purchase time.
* Triggering rule.
* Purchase status.

Example:

```text
Plush Pepe #1842

Green / Star Pattern

Куплен за: 85 TON
Floor price: 102 TON
Разница: +20%

Правило: Pepe до 90 TON
2 минуты назад
```

### Gift Card Actions

Support:

* Open details.
* Open in Telegram.
* Copy gift link.
* View triggering rule.
* Create similar rule.
* Mark as sold.
* Add a note.

Do not put every action directly on the card. Use a compact action menu.

### Gift Details

The detail panel should show:

* Full gift metadata.
* Collection.
* Model.
* Backdrop.
* Symbol or pattern.
* Rarity.
* Gift number.
* Purchase price.
* Fees.
* Effective total cost.
* Current market estimate.
* Purchase timestamp.
* Transaction identifier.
* Triggering rule.
* Raw marketplace link.
* Purchase execution logs.

Avoid displaying raw technical data unless the user expands an advanced section.

---

## Purchased Gift Filters

Support:

* Search by name or number.
* Collection.
* Rule.
* Purchase date.
* Price range.
* Profitability.
* Purchase status.
* Sold or unsold state.

Sorting options:

* Newest.
* Oldest.
* Lowest purchase price.
* Highest purchase price.
* Highest estimated profit.
* Lowest estimated profit.

View options:

* Cards.
* Table.

Preserve selected filters in the URL when practical.

Example:

```text
/dashboard?collection=plush-pepes&sort=newest
```

---

## Bot Activity

Show a compact real-time activity indicator.

Example:

```text
Бот активен · проверено 1 284 подарка · последняя проверка 2 сек. назад
```

Activity information may include:

* Gifts scanned.
* Matches found.
* Purchases completed.
* Purchases skipped.
* Last successful connection.
* Marketplace latency.

Avoid fake real-time values.

If live data is unavailable, clearly label the data as delayed or simulated.

---

## Notifications

Support notifications for:

* Successful purchase.
* Failed purchase.
* Insufficient balance.
* Rule budget reached.
* Global budget reached.
* Bot disconnected.
* Rule automatically paused.
* Suspicious price.
* Purchase skipped.

Notifications should include a clear reason and, when possible, a direct action.

Example:

```text
Покупка пропущена

Plush Pepe #1842 подходил под правило,
но дневной лимит расходов уже достигнут.

[Открыть правило]
```

Use toast notifications for temporary feedback and a notification center for persistent events.

---

## Empty States

Every major area must have a meaningful empty state.

### No Rules

```text
У вас пока нет правил автопокупки.

Создайте первое правило, выберите коллекцию
и укажите максимальную цену.

[Создать правило]
```

### No Purchased Gifts

```text
Бот ещё ничего не купил.

Подходящие подарки появятся здесь после
срабатывания активного правила.
```

### No Filter Results

```text
По выбранным фильтрам ничего не найдено.

[Сбросить фильтры]
```

Do not use generic text such as “No data”.

---

## Loading States

Use skeletons that resemble the final layout.

Provide skeletons for:

* Rule cards.
* Gift cards.
* Balance metrics.
* Bot status.
* Filters.
* Gift details.

Avoid full-page spinners unless the application cannot render any useful shell.

Optimistic updates may be used for:

* Pause/resume rule.
* Changing priority.
* Marking a gift as sold.

Rollback optimistic changes if the request fails.

---

## Error Handling

Errors must be actionable.

Bad:

```text
Something went wrong.
```

Good:

```text
Не удалось включить правило.

Соединение с ботом потеряно.
Проверьте подключение аккаунта и повторите попытку.

[Повторить]
```

Handle at least:

* Network error.
* Unauthorized session.
* Bot disconnected.
* Marketplace unavailable.
* Validation error.
* Insufficient funds.
* Duplicate rule.
* Purchase conflict.
* Rate limit.
* Unknown server error.

Log technical details separately from user-facing messages.

Never expose secrets, tokens, stack traces, or raw server errors in the UI.

---

## Visual Direction

Use a dark, restrained, premium interface.

Recommended characteristics:

* Near-black page background.
* Slightly lighter panel surfaces.
* Thin neutral borders.
* White primary text.
* Muted gray secondary text.
* One accent color.
* Gift images as the main colorful visual element.
* Border radius around 12–16 px.
* Minimal shadows.
* Clear spacing hierarchy.

Avoid:

* Gradients unless extremely subtle.
* Glassmorphism.
* Strong glow effects.
* Neon green crypto styling.
* Excessive animations.
* Decorative charts without useful data.
* Oversized headings.
* Too many accent colors.

The interface should resemble a professional monitoring dashboard rather than a trading casino.

---

## Design Tokens

Use semantic design tokens instead of hardcoded colors.

Example:

```css
--background
--surface
--surface-elevated
--border
--text-primary
--text-secondary
--accent
--success
--warning
--danger
```

Use consistent spacing and radius values.

Suggested spacing scale:

```text
4, 8, 12, 16, 20, 24, 32, 40
```

Suggested radii:

```text
8, 12, 16
```

Do not introduce arbitrary values unless required by the design.

---

## Accessibility

All interactive elements must be keyboard accessible.

Requirements:

* Visible focus states.
* Proper labels for form fields.
* Semantic buttons.
* ARIA labels for icon-only buttons.
* Sufficient contrast.
* Status conveyed by text, not color alone.
* Dialog focus trapping.
* Escape closes modal or panel when safe.
* Confirmation before destructive actions.
* Logical tab order.

Switches must include readable labels.

Bad:

```tsx
<Switch />
```

Good:

```tsx
<label>
  <Switch />
  Правило активно
</label>
```

---

## Data Models

Use explicit TypeScript types.

Example:

```ts
type RuleStatus =
  | "active"
  | "paused"
  | "disabled"
  | "budget_reached"
  | "insufficient_balance"
  | "connection_error";

type PurchaseRule = {
  id: string;
  name: string;
  description?: string;
  status: RuleStatus;
  priority: number;
  collectionIds: string[];
  modelIds: string[];
  backdropIds: string[];
  symbolIds: string[];
  maximumPriceTon: number;
  minimumPriceTon?: number;
  maximumPurchasesPerDay?: number;
  maximumSpendPerDayTon?: number;
  maximumIdenticalGifts?: number;
  cooldownSeconds?: number;
  createdAt: string;
  updatedAt: string;
};

type PurchasedGift = {
  id: string;
  name: string;
  collectionName: string;
  modelName?: string;
  backdropName?: string;
  symbolName?: string;
  giftNumber?: number;
  imageUrl?: string;
  purchasePriceTon: number;
  feesTon?: number;
  currentFloorPriceTon?: number;
  purchasedAt: string;
  ruleId: string;
  ruleName: string;
  telegramUrl?: string;
  status: "purchased" | "pending" | "failed" | "sold";
};
```

Do not use `any`.

Prefer discriminated unions for condition types.

Example:

```ts
type PriceCondition =
  | {
      type: "fixed_maximum";
      maximumPriceTon: number;
    }
  | {
      type: "below_floor";
      percentageBelowFloor: number;
    };
```

---

## API Conventions

Keep API communication separate from UI components.

Suggested structure:

```text
src/
  app/
  components/
  features/
    purchase-rules/
    purchased-gifts/
    bot-status/
    notifications/
  lib/
    api/
    validation/
    utils/
  stores/
  types/
```

Use feature-based modules where practical.

API functions should:

* Have typed inputs.
* Have typed outputs.
* Normalize errors.
* Handle cancellation.
* Avoid leaking transport details into components.

Example:

```ts
async function createPurchaseRule(
  input: CreatePurchaseRuleInput
): Promise<PurchaseRule> {
  // API implementation
}
```

Do not call `fetch` directly from deeply nested presentation components.

---

## Mock Data

When backend endpoints are unavailable, create realistic mock data.

Mock data must:

* Be clearly isolated.
* Be easy to replace.
* Never be presented as real production data.
* Include loading, error, empty, and populated scenarios.
* Include long names and edge cases.

Create at least:

* 3 active rules.
* 1 paused rule.
* 1 rule with an error.
* 8 purchased gifts.
* 1 pending purchase.
* 1 failed purchase.

Do not hardcode mock data directly inside page components.

---

## Security

Never store Telegram session data, bot tokens, private keys, or access tokens in client-side code.

Do not:

* Put secrets in `NEXT_PUBLIC_*` variables.
* Log tokens.
* Expose raw authentication data.
* Store sensitive credentials in localStorage.
* Include private keys in mock data.

All purchase execution must happen on a trusted backend.

The frontend may request an action but must never execute marketplace purchases directly.

All destructive or financial actions should be verified server-side.

---

## Financial Safety

This application can spend real funds. Financial actions require extra care.

Always include:

* Explicit price display.
* Currency display.
* Purchase limits.
* Confirmation for high-risk changes.
* Emergency stop.
* Server-side validation.
* Idempotency for purchase requests.
* Protection against duplicate purchases.
* Clear fee calculations.
* Audit logs.

Never silently increase limits.

Never activate a newly created rule when required values are incomplete.

When editing an active rule, clearly indicate whether changes apply immediately.

---

## Component Guidelines

Components should be:

* Focused.
* Reusable.
* Typed.
* Accessible.
* Easy to test.

Prefer composition over large conditional components.

Suggested components:

```text
DashboardHeader
BotStatusBadge
EmergencyStopButton
RuleList
RuleCard
RuleStatusBadge
RuleFormDrawer
RuleSummary
CollectionMultiSelect
PriceConditionFields
RuleLimitsFields
PurchasedGiftGrid
PurchasedGiftCard
PurchasedGiftTable
PurchasedGiftFilters
GiftDetailsDrawer
ActivityFeed
NotificationCenter
EmptyState
ErrorState
ConfirmDialog
```

Avoid creating a single page component containing the entire application.

---

## State Management

Use local component state for:

* Open/closed dialogs.
* Temporary form state.
* Hover and selection state.

Use URL state for:

* Search query.
* Filters.
* Sorting.
* View mode.
* Pagination.

Use server state tools for:

* Rules.
* Purchased gifts.
* Bot status.
* Balance.
* Notifications.

Use global client state only for truly global UI state.

Do not put all state into Zustand by default.

---

## Forms

All forms should use:

* React Hook Form.
* Zod validation.
* Accessible field labels.
* Inline error messages.
* Disabled submit state while saving.
* Dirty state tracking.
* Unsaved changes confirmation.

Do not close a form before the server confirms success.

After saving:

* Update cached data.
* Show a success notification.
* Keep the user’s scroll position.
* Highlight the created or edited rule briefly.

---

## Animations

Animations should be subtle and functional.

Allowed:

* Drawer transitions.
* Modal transitions.
* Small status changes.
* Reordering feedback.
* Card insertion.
* Skeleton loading.

Avoid:

* Constant pulsing.
* Large background motion.
* Confetti.
* Excessive spring effects.
* Animations longer than necessary.

Respect reduced-motion preferences.

---

## Testing

Add tests for important financial and rule logic.

Prioritize:

* Rule validation.
* Price condition evaluation.
* Global limit overrides.
* Daily budget calculations.
* Duplicate purchase prevention.
* Pause/resume behaviour.
* Filter logic.
* Profit calculation.
* Form submission.

Suggested tools:

* Vitest
* React Testing Library
* Playwright

At minimum, test the critical user flow:

1. Create a rule.
2. Set a maximum price.
3. Set a daily limit.
4. Enable the rule.
5. Confirm the rule appears in the list.
6. Pause the rule.
7. Open a purchased gift.
8. Filter gifts by rule.

Do not rely only on snapshot tests.

---

## Code Quality

Before completing a task:

1. Run formatting.
2. Run linting.
3. Run TypeScript checks.
4. Run relevant tests.
5. Check desktop layout.
6. Check mobile layout.
7. Check loading states.
8. Check empty states.
9. Check errors.
10. Check keyboard navigation.

Common commands may include:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

Use the package manager already present in the repository.

Do not generate a new lockfile with a different package manager.

---

## Agent Behaviour

When working on this repository:

1. Inspect the existing project before writing code.
2. Reuse existing components and conventions.
3. Make the smallest coherent change that solves the task.
4. Do not rewrite unrelated areas.
5. Do not remove working functionality without explanation.
6. Keep financial safety visible in all purchase-related flows.
7. Implement complete UI states, not only the ideal state.
8. Avoid placeholder buttons that do nothing.
9. Do not fabricate backend functionality.
10. Clearly mark mocked behaviour.
11. Keep the interface in Russian.
12. Keep code and types in English.
13. Run available checks before finishing.
14. Report files changed and checks performed.

When requirements are incomplete, make reasonable product decisions based on this document and preserve extensibility.

---

## Definition of Done

A feature is complete only when:

* It works in the intended user flow.
* It matches the visual direction.
* It is responsive.
* It is accessible.
* It handles loading.
* It handles errors.
* It handles empty states.
* It uses typed data.
* It does not expose secrets.
* It respects global and rule-level limits.
* It passes available linting and type checks.
* It does not introduce unrelated regressions.

A visually complete screen with non-working actions is not considered done.
