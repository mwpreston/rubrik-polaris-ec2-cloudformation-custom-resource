# Rubrik::Polaris::EC2Instance

A resource to manage EC2 Instances protected by Rubrik on Rubrik Polaris

## Syntax

To declare this entity in your AWS CloudFormation template, use the following syntax:

### JSON

<pre>
{
    "Type" : "Rubrik::Polaris::EC2Instance",
    "Properties" : {
        "<a href="#ec2instanceid" title="EC2InstanceId">EC2InstanceId</a>" : <i>String</i>,
        "<a href="#sladomainname" title="SLADomainName">SLADomainName</a>" : <i>String</i>,
        "<a href="#awsaccountid" title="AWSAccountId">AWSAccountId</a>" : <i>String</i>,
    }
}
</pre>

### YAML

<pre>
Type: Rubrik::Polaris::EC2Instance
Properties:
    <a href="#ec2instanceid" title="EC2InstanceId">EC2InstanceId</a>: <i>String</i>
    <a href="#sladomainname" title="SLADomainName">SLADomainName</a>: <i>String</i>
    <a href="#awsaccountid" title="AWSAccountId">AWSAccountId</a>: <i>String</i>
</pre>

## Properties

#### EC2InstanceId

ID of the EC2 Instance (AWS)

_Required_: No

_Type_: String

_Update requires_: [No interruption](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html#update-no-interrupt)

#### SLADomainName

Name of the Rubrik SLA Domain

_Required_: No

_Type_: String

_Update requires_: [No interruption](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html#update-no-interrupt)

#### AWSAccountId

Account ID of current AWS Account

_Required_: No

_Type_: String

_Update requires_: [No interruption](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html#update-no-interrupt)

## Return Values

### Fn::GetAtt

The `Fn::GetAtt` intrinsic function returns a value for a specified attribute of this type. The following are the available attributes and sample return values.

For more information about using the `Fn::GetAtt` intrinsic function, see [Fn::GetAtt](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-getatt.html).

#### ID

ID is automatically generated within Rubrik Polaris

#### Content

Variable content

#### SecretName

Name of secret containing polaris domain and credentials

