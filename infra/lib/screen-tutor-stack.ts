import * as path from "node:path";
import * as cdk from "aws-cdk-lib";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import { Platform } from "aws-cdk-lib/aws-ecr-assets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import type { Construct } from "constructs";

export interface Settings {
  nebiusApiKey: string;
  accessToken: string;
  tavilyApiKey: string;
  modelName: string;
  modelExtraBody: string;
  modelFallbackName: string;
}

// The backend (FastAPI) as a Lambda container image on Graviton (arm64), behind a
// public HTTPS Function URL. Requests to /explain-turn need the access token.
//
// The keys are passed as environment variables of the function: encrypted at rest
// by AWS, visible to administrators of this account. Fine for a personal project;
// use Secrets Manager or Parameter Store for anything shared.
export class ScreenTutorStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps & { settings: Settings }) {
    super(scope, id, props);
    const { settings } = props;

    const logGroup = new logs.LogGroup(this, "Logs", {
      logGroupName: "/screen-tutor/explain",
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const fn = new lambda.DockerImageFunction(this, "ExplainFunction", {
      functionName: "screen-tutor-explain",
      description: "Sherpa Explain Turn service (OpenCV 5 + vision model), arm64",
      code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, "..", "..", "backend"), {
        platform: Platform.LINUX_ARM64,
      }),
      architecture: lambda.Architecture.ARM_64,
      memorySize: 2048,
      timeout: cdk.Duration.seconds(120),
      logGroup,
      environment: {
        MODEL_ADAPTER: "nebius",
        MODEL_NAME: settings.modelName,
        // Lambda Web Adapter streams the response as it is written (needed for live steps).
        AWS_LWA_INVOKE_MODE: "response_stream",
        NEBIUS_API_KEY: settings.nebiusApiKey,
        BACKEND_ACCESS_TOKEN: settings.accessToken,
        ...(settings.tavilyApiKey ? { TAVILY_API_KEY: settings.tavilyApiKey } : {}),
        ...(settings.modelExtraBody ? { MODEL_EXTRA_BODY: settings.modelExtraBody } : {}),
        ...(settings.modelFallbackName !== undefined ? { MODEL_FALLBACK_NAME: settings.modelFallbackName } : {}),
      },
    });

    // RESPONSE_STREAM lets the steps of an answer reach the client one by one while
    // the model is still writing, instead of all at the end.
    const url = fn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      invokeMode: lambda.InvokeMode.RESPONSE_STREAM,
    });

    // Metrics written by the service (embedded metric format) and by Lambda itself.
    const metric = (name: string, statistic: string) =>
      new cloudwatch.Metric({
        namespace: "ScreenTutor",
        metricName: name,
        dimensionsMap: { Model: settings.modelName },
        statistic,
        period: cdk.Duration.minutes(5),
      });
    const dashboard = new cloudwatch.Dashboard(this, "Dashboard", { dashboardName: "screen-tutor" });
    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: "Turn latency (ms)",
        left: [metric("TurnLatencyMs", "Average"), metric("TurnLatencyMs", "p95")],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: "Model latency (ms) and region proposer (ms)",
        left: [metric("ModelLatencyMs", "Average"), metric("RegionsLatencyMs", "Average")],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: "Turns and failures",
        left: [fn.metricInvocations({ period: cdk.Duration.minutes(5) }), metric("TurnFailures", "Sum")],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: "Model attempts (average, 1 = no retry)",
        left: [metric("Attempts", "Average")],
        width: 12,
      }),
    );

    new cdk.CfnOutput(this, "FunctionUrl", { value: url.url, description: "Public HTTPS address of the backend" });
    new cdk.CfnOutput(this, "Architecture", { value: "arm64 (AWS Graviton)" });
  }
}
