#!/usr/bin/env python3
"""Build a standalone CloudFormation template with inline Python Lambda code.

No build container, deployment bucket, SAM, CDK or packaging service is required.
Run this script after changing either Lambda; commit the generated template.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ref(name):
    return {"Ref": name}


def sub(value):
    return {"Fn::Sub": value}


def arn(name):
    return {"Fn::GetAtt": [name, "Arn"]}


def log_permissions(log_group):
    return {
        "Effect": "Allow",
        "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource": sub(f"arn:${{AWS::Partition}}:logs:${{AWS::Region}}:${{AWS::AccountId}}:log-group:/aws/lambda/${{LabName}}-{log_group}:*"),
    }


def role(statements):
    return {
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}],
            },
            "Policies": [{"PolicyName": "replayguard-minimum", "PolicyDocument": {"Version": "2012-10-17", "Statement": statements}}],
        },
    }


def build_template(experiment="baseline"):
    if experiment not in ("baseline", "key-scope"):
        raise ValueError("Unknown experiment")
    source_prefix = "key_" if experiment == "key-scope" else ""
    resources = {
        "Ledger": {
            "Type": "AWS::DynamoDB::Table",
            "Properties": {
                "TableName": sub("${LabName}-receipts"),
                "BillingMode": "PAY_PER_REQUEST",
                "OnDemandThroughput": {"MaxReadRequestUnits": 5, "MaxWriteRequestUnits": 5},
                "AttributeDefinitions": [{"AttributeName": "PK", "AttributeType": "S"}, {"AttributeName": "SK", "AttributeType": "S"}],
                "KeySchema": [{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
                "SSESpecification": {"SSEEnabled": True},
                "TimeToLiveSpecification": {"AttributeName": "expiresAt", "Enabled": True},
                "Tags": [{"Key": "Project", "Value": "ReplayGuard"}, {"Key": "LabExpiresAt", "Value": ref("LabExpiresAt")}],
            },
        },
        "DeadLetterQueue": {
            "Type": "AWS::SQS::Queue",
            "Properties": {
                "QueueName": sub("${LabName}-dlq"), "SqsManagedSseEnabled": True,
                "MessageRetentionPeriod": 86400, "MaximumMessageSize": 4096,
                "Tags": [{"Key": "Project", "Value": "ReplayGuard"}],
            },
        },
        "OrdersQueue": {
            "Type": "AWS::SQS::Queue",
            "Properties": {
                "QueueName": sub("${LabName}-orders"), "SqsManagedSseEnabled": True,
                "VisibilityTimeout": 72, "MessageRetentionPeriod": 3600,
                "MaximumMessageSize": 4096, "ReceiveMessageWaitTimeSeconds": 20,
                "RedrivePolicy": {"deadLetterTargetArn": arn("DeadLetterQueue"), "maxReceiveCount": 3},
                "Tags": [{"Key": "Project", "Value": "ReplayGuard"}],
            },
        },
        "WorkerLogs": {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": sub("/aws/lambda/${LabName}-worker"), "RetentionInDays": 1}},
        "ProviderLogs": {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": sub("/aws/lambda/${LabName}-provider"), "RetentionInDays": 1}},
        "ProviderRole": role([
            log_permissions("provider"),
            {"Effect": "Allow", "Action": ["dynamodb:PutItem", "dynamodb:GetItem"], "Resource": arn("Ledger")},
        ]),
        "WorkerRole": role([
            log_permissions("worker"),
            {"Effect": "Allow", "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], "Resource": arn("OrdersQueue")},
            {"Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": arn("ProviderFunction")},
        ]),
        "ProviderFunction": {
            "Type": "AWS::Lambda::Function", "DependsOn": "ProviderLogs",
            "Properties": {
                "FunctionName": sub("${LabName}-provider"), "Runtime": "python3.12", "Handler": "index.handler",
                "Role": arn("ProviderRole"), "Timeout": 6, "MemorySize": 512,
                "ReservedConcurrentExecutions": {"Fn::If": ["HasReservation", ref("ReservedConcurrency"), ref("AWS::NoValue")]},
                "Architectures": ["arm64"],
                "Environment": {"Variables": {"LEDGER_TABLE": ref("Ledger"), "LAB_EXPIRES_AT": ref("LabExpiresAt")}},
                "Code": {"ZipFile": (ROOT / ("src/" + source_prefix + "provider.py")).read_text()},
                "Tags": [{"Key": "Project", "Value": "ReplayGuard"}],
            },
        },
        "WorkerFunction": {
            "Type": "AWS::Lambda::Function", "DependsOn": "WorkerLogs",
            "Properties": {
                "FunctionName": sub("${LabName}-worker"), "Runtime": "python3.12", "Handler": "index.handler",
                "Role": arn("WorkerRole"), "Timeout": 12, "MemorySize": 512,
                "ReservedConcurrentExecutions": {"Fn::If": ["HasReservation", ref("ReservedConcurrency"), ref("AWS::NoValue")]},
                "Architectures": ["arm64"],
                "Environment": {"Variables": {"PROVIDER_FUNCTION_ARN": arn("ProviderFunction"), "LAB_EXPIRES_AT": ref("LabExpiresAt")}},
                "Code": {"ZipFile": (ROOT / ("src/" + source_prefix + "worker.py")).read_text()},
                "Tags": [{"Key": "Project", "Value": "ReplayGuard"}],
            },
        },
        "WorkerQueueMapping": {
            "Type": "AWS::Lambda::EventSourceMapping",
            "Properties": {
                "EventSourceArn": arn("OrdersQueue"), "FunctionName": ref("WorkerFunction"),
                "BatchSize": 1, "MaximumBatchingWindowInSeconds": 0,
                "Enabled": True, "ScalingConfig": {"MaximumConcurrency": 2},
            },
        },
    }
    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "ReplayGuard: bounded, expiring SQS/Lambda failure lab and independent simulated fulfillment receipts.",
        "Parameters": {
            "LabName": {"Type": "String", "Default": "replayguard", "MinLength": 3, "MaxLength": 32, "AllowedPattern": "[a-z][a-z0-9-]{2,31}", "Description": "Unique short resource prefix."},
            "LabExpiresAt": {"Type": "String", "AllowedPattern": "[0-9]{10}", "Description": "UTC Unix epoch after which both Lambdas reject fulfillment; deploy script permits 1-48 hours, default 24. Delete stack after use."},
            "ReservedConcurrency": {"Type": "Number", "Default": 2, "AllowedValues": [-1, 2], "Description": "Use 2 when the regional quota permits reservations. Use -1 for low-quota student accounts; the private SQS mapping still caps worker concurrency at 2."},
        },
        "Conditions": {"HasReservation": {"Fn::Equals": [ref("ReservedConcurrency"), 2]}},
        "Resources": resources,
        "Outputs": {
            "QueueUrl": {"Value": ref("OrdersQueue")}, "DlqUrl": {"Value": ref("DeadLetterQueue")},
            "LedgerTable": {"Value": ref("Ledger")},
            "WorkerLogGroup": {"Value": ref("WorkerLogs")}, "ProviderLogGroup": {"Value": ref("ProviderLogs")},
            "WorkerFunctionName": {"Value": ref("WorkerFunction")}, "ProviderFunctionName": {"Value": ref("ProviderFunction")},
            "Region": {"Value": ref("AWS::Region")}, "Expiry": {"Value": ref("LabExpiresAt")},
        },
    }
    if experiment == "key-scope":
        template["Outputs"].update({"Experiment": {"Value": "key-scope"}, "MappingId": {"Value": ref("WorkerQueueMapping")}})
    return template


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=("baseline", "key-scope"), default="baseline")
    args = parser.parse_args()
    target = ROOT / ("infra/template-key-scope.json" if args.experiment == "key-scope" else "infra/template.json")
    target.write_text(json.dumps(build_template(args.experiment), indent=2) + "\n")
    print(f"Generated {target.relative_to(ROOT)} ({target.stat().st_size:,} bytes)")
