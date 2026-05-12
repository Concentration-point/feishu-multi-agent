/**
 * 一次性 fixture 测试 runner。
 *
 * 因为项目暂未引入 vitest，临时用这个脚本驱动 fromEvents.test.ts 里的 runFixtureTests()。
 * 用法（不会污染 package.json devDependencies）：
 *   npx --yes tsx scripts/run-fixture-tests.ts
 *
 * 退出码：0=全通过，1=有 failure。
 */

import { runFixtureTests } from "../src/console/selectors/__tests__/fromEvents.test";

const { assertions, failures } = runFixtureTests();

console.log(`fixture assertions: ${assertions}`);
console.log(`fixture failures:   ${failures.length}`);

for (const msg of failures) {
  console.error(msg);
}

process.exit(failures.length === 0 ? 0 : 1);
