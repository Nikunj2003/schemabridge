import { Upload } from "@/components/upload";

/** Landing: explain the product in a sentence, then get out of the way. */
export default function Page() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-5xl flex-col justify-center px-6 py-16">
      <div className="max-w-2xl">
        <h1 className="font-display text-[34px] leading-[1.15] font-semibold tracking-tight">
          Migrate inconsistent exports without checking every field
        </h1>
        <p className="mt-4 max-w-xl text-[14.5px] leading-relaxed text-muted-foreground">
          SchemaBridge reads several exports of the same data, works out how they
          map onto the target schema, cleans what it safely can, and pushes the
          result to the destination. It asks you only about the decisions that
          genuinely need judgement.
        </p>
      </div>

      <div className="mt-10">
        <Upload maxFiles={3} />
      </div>

      <p className="mt-12 max-w-xl text-[12px] leading-relaxed text-muted-foreground">
        A demonstration on synthetic data. Do not upload real personal
        information.
      </p>
    </main>
  );
}
