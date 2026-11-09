/**
 * Narrow ambient boundary for the external Cordis package.
 *
 * Vitest resolves `@deepseek-ai/cordis` to the real source in the read-only DSH
 * checkout. TypeScript uses this declaration so our package can enforce full
 * strictness without compiling the vendor source under a different tsconfig.
 * Only the API surface used by pipeline_v2 is declared here.
 */
declare module '@deepseek-ai/cordis' {
  export interface Disposable<T = unknown> {
    (): T
  }

  export interface Fiber {
    readonly dispose: () => Promise<void>
  }

  export interface PluginObject<Config = unknown> {
    readonly name?: string
    readonly inject?: readonly string[]
    apply(ctx: Context, config: Config): void | Promise<void>
  }

  export namespace Plugin {
    type Object<Config = unknown> = PluginObject<Config>
  }

  export type PluginInput =
    | PluginObject<any>
    | ((ctx: Context) => unknown)
    | (new (ctx: Context) => unknown)

  export interface Context {
    effect(execute: () => Disposable | (() => void), label?: string): Disposable
    plugin(plugin: PluginInput, ...args: any[]): Fiber & PromiseLike<Fiber>
  }

  export class Context {
    constructor()
  }

  export class Service {
    constructor(ctx: Context, name: string)
  }
}
