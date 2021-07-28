# Third-party CloudFormation resource for Rubrik Polaris EC2 Protection

A CloudFormation custom resource type for managing EC2 workloads within Polaris

# Introduction

The `Rubrik::Polaris::EC2Instance` is a CloudFormation resource type created in order to allow users to modify the SLA Domains assigned to EC2 instances within Rubrik Polaris.

This allows for end users to control the data protection constructs of their EC2 instances directly from within CloudFormation stacks

# Prerequisites

The following packages are required in order to install and consume the `Rubrik::Polaris::EC2Instance` third-party custom resource within AWS CloudFormation

* [AWS CLI]
* AWS SecretsManager object containing fqdn and credentials to use to connect to Rubrik Polaris

# User Installation  43

*Step 1:* Clone this repository using the following commands
```
git clone https://github.com/mwpreston/rubrik-polaris-ec2-cloudformation-custom-resource.git
```

*Step 2:* Deploy the custom resource to the desired region using the following commands
```
cfn submit -v --set-default --region us-east-1
```

This will result in the following being deployed within your AWS organization

* The `Rubrik::Polaris::EC2Instance` resource type
* An IAM Role containing the nessessary permisions to read from AWS SecretsManager

# Documentation

# Change Log