import * as path from "node:path";
import * as cdk from "aws-cdk-lib";
import { Platform } from "aws-cdk-lib/aws-ecr-assets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import type { Construct } from "constructs";

// Two copies of the backend, one on Graviton (arm64) and one on x86_64, with the same image
// code, memory and settings, and with the canned model (MODEL_ADAPTER=fake) so that what is
// measured is the compute: OpenCV region proposing and building the answer. Deployed only for the
// benchmark (`cdk deploy ScreenTutorBenchmark -c benchmark=true`) and destroyed afterwards.
export class BenchmarkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps & { accessToken: string; memoryMb: number }) {
    super(scope, id, props);
    for (const [arch, architecture, platform] of [
      ["arm64", lambda.Architecture.ARM_64, Platform.LINUX_ARM64],
      ["x86", lambda.Architecture.X86_64, Platform.LINUX_AMD64],
    ] as const) {
      const fn = new lambda.DockerImageFunction(this, `Bench${arch}`, {
        functionName: `screen-tutor-bench-${arch}`,
        code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, "..", "..", "backend"), { platform }),
        architecture,
        memorySize: props.memoryMb,
        timeout: cdk.Duration.seconds(60),
        environment: {
          MODEL_ADAPTER: "fake",
          BACKEND_ACCESS_TOKEN: props.accessToken,
          RATE_LIMIT_PER_MINUTE: "100000",
        },
      });
      const url = fn.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.NONE });
      new cdk.CfnOutput(this, `Url${arch}`, { value: url.url });
    }
  }
}
