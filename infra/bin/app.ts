#!/usr/bin/env node
// Reads the deployment settings from the git-ignored .env at the repository root.
import * as path from "node:path";
import * as cdk from "aws-cdk-lib";
import * as dotenv from "dotenv";
import { BenchmarkStack } from "../lib/benchmark-stack";
import { SherpaStack } from "../lib/sherpa-stack";

dotenv.config({ path: path.join(__dirname, "..", "..", ".env") });

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} must be set in .env before deploying (see .env.example)`);
  return value;
}

const app = new cdk.App();
new SherpaStack(app, "Sherpa", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.AWS_REGION ?? process.env.CDK_DEFAULT_REGION ?? "us-east-1",
  },
  settings: {
    nebiusApiKey: required("NEBIUS_API_KEY"),
    accessToken: required("BACKEND_ACCESS_TOKEN"),
    tavilyApiKey: process.env.TAVILY_API_KEY ?? "",
    modelName: process.env.MODEL_NAME ?? "deepseek-ai/DeepSeek-V4.1-Flash",
    modelExtraBody: process.env.MODEL_EXTRA_BODY ?? "",
    // Empty string switches the second model (hedged requests) off.
    modelFallbackName: process.env.MODEL_FALLBACK_NAME ?? "Qwen/Qwen3.8-27B",
  },
});

// The benchmark pair (arm64 and x86), only when asked for: `-c benchmark=true`.
if (app.node.tryGetContext("benchmark") === "true") {
  new BenchmarkStack(app, "SherpaBenchmark", {
    env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.AWS_REGION ?? process.env.CDK_DEFAULT_REGION ?? "us-east-1" },
    accessToken: required("BACKEND_ACCESS_TOKEN"),
    memoryMb: Number(process.env.BENCH_MEMORY_MB ?? 2048),
  });
}

// The stack of the earlier name: an empty definition, only so that `cdk destroy ScreenTutor -c legacy=true`
// can remove what is left of it.
if (app.node.tryGetContext("legacy") === "true") {
  new cdk.Stack(app, "ScreenTutor", {
    env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.AWS_REGION ?? process.env.CDK_DEFAULT_REGION ?? "us-east-1" },
  });
}
