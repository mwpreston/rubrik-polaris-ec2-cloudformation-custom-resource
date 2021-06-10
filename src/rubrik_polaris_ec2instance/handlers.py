import logging
import json
import boto3
import requests
import time
import base64
from botocore.exceptions import ClientError

from typing import Any, MutableMapping, Optional
from cloudformation_cli_python_lib import (
    Action,
    HandlerErrorCode,
    OperationStatus,
    ProgressEvent,
    Resource,
    SessionProxy,
    exceptions,
    identifier_utils,
)

from .models import ResourceHandlerRequest, ResourceModel

# Use this logger to forward log messages to CloudWatch Logs.
LOG = logging.getLogger(__name__)
TYPE_NAME = "Rubrik::Polaris::EC2Instance"

resource = Resource(TYPE_NAME, ResourceModel)
test_entrypoint = resource.test_entrypoint

REFRESH_ACCOUNT_QUERY = """mutation RefreshAWSAccountsMutation($input: StartAwsNativeAccountsRefreshJobInput!) {
    startRefreshAwsNativeAccountsJob(input: $input) {
        jobIds {
        rubrikObjectId
        jobId
        __typename
        }
        errors {
        rubrikObjectId
        error
        __typename
        }
        __typename
    }
}"""

LIST_ALL_INSTANCES_QUERY  = """query EC2InstancesListQuery($filters: AwsNativeEc2InstanceFilters) {
    awsNativeEc2Instances(    ec2InstanceFilters: $filters) {
        edges {
        node {
            id
            instanceNativeId
            instanceName
            vpcName
            region
            vpcId
            isRelic
            effectiveSlaDomain {
            id
            name
            }
            instanceType
            slaAssignment
        }
        }
    }
}"""

JOB_MONITOR_QUERY = """
    query EventSeriesDetailsQuery($activitySeriesId: UUID!, $clusterUuid: UUID) {
    activitySeries(activitySeriesId: $activitySeriesId, clusterUuid: $clusterUuid) {
        activityConnection {
        nodes {
            activityInfo
            message
            status
            time
            severity
            __typename
        }
        __typename
        }
        ...EventSeriesFragment
        startTime
        cluster {
        id
        name
        clusterNodeConnection {
            nodes {
            ipAddress
            __typename
            }
            __typename
        }
        __typename
        }
        __typename
    }
    }

    fragment EventSeriesFragment on ActivitySeries {
    id
    fid
    activitySeriesId
    lastUpdated
    lastActivityType
    lastActivityStatus
    objectId
    objectName
    objectType
    severity
    progress
    isCancelable
    isPolarisEventSeries
    __typename
}"""


def retrieve_headers(session, model):
    LOG.warning("Retrieving authentication headers")
    secret = get_secret(session, model.SecretName)
    polaris_username = json.loads(secret['SecretString'])['PolarisUsername']
    polaris_password = json.loads(secret['SecretString'])['PolarisPassword']
    polaris_domain = json.loads(secret['SecretString'])['PolarisDomain']
    payload = {'username':polaris_username, 'password':polaris_password, 'domain_type': 'localOrSSO'}
    authheaders = {'content_type':'application/json'}
    url = "https://" + polaris_domain + "/api/session"
    r = requests.post(url, json=payload,headers=authheaders)
    access_token = r.json()['access_token']
    LOG.warning("Building new headers with access token of " + access_token)
    headers = {'Authorization': 'Bearer ' + access_token}
    graphurl = 'https://' + polaris_domain + '/api/graphql'
    return headers, graphurl

def retrieve_access_token(url,username,password):
    LOG.warning("I'm getting an access token")
    payload = {'username':username, 'password':password, 'domain_type': 'localOrSSO'}
    #LOG.info("payload is " + payload)
    headers = {'content_type':'application/json'}
    url = "https://" + url + "/api/session"
    LOG.warning("url is " + url)
    r = requests.post(url, json=payload,headers=headers)
    access_token = r.json()['access_token']

    return access_token

def refresh_aws_account(model,headers,graphurl):

    # Need to get Rubrik ID of AWS Account
    operation_name = "CloudAccountsNativeProtectionListQuery"
    query = """query CloudAccountsNativeProtectionListQuery($awsCloudAccountsArg: AwsCloudAccountsInput!) {
    allAwsCloudAccounts(awsCloudAccountsArg: $awsCloudAccountsArg) {
        awsCloudAccount {
        id
        nativeId
        accountName
        cloudType
        seamlessFlowEnabled
        __typename
        }
        featureDetails {
        feature
        roleArn
        stackArn
        status
        awsRegions
        __typename
        }
        __typename
    }
    }"""
    variables = {
    "awsCloudAccountsArg": {
        "feature": "CLOUD_NATIVE_PROTECTION",
        "columnSearchFilter": model.AWSAccountId,
        "statusFilters": []
    }
    }
    payload = {
        "operationName": operation_name,
        "variables": variables,
        "query": query
    }
    r = requests.post(graphurl, json=payload, headers=headers)
    aws_account_rubrik_id = r.json()['data']['allAwsCloudAccounts'][0]['awsCloudAccount']['id']

    operation_name = "RefreshAWSAccountsMutation"
    variables = {
        "input": {
            "awsAccountRubrikIds": [
            aws_account_rubrik_id
            ],
            "awsNativeProtectionFeatures": [
            "EC2"
            ]
        }
    }
    query = """mutation RefreshAWSAccountsMutation($input: StartAwsNativeAccountsRefreshJobInput!) {
        startRefreshAwsNativeAccountsJob(input: $input) {
            jobIds {
            rubrikObjectId
            jobId
            __typename
            }
            errors {
            rubrikObjectId
            error
            __typename
            }
            __typename
        }
    }"""
    payload = {
        "operationName": operation_name,
        "variables": variables,
        "query": query
    }
    r = requests.post(graphurl, json=payload, headers=headers)
    LOG.warning("Refresh job submitted, let's make sure it starts..")
    # Refresh initiated - now let's monitor the job start
    while len(r.json()['data']['startRefreshAwsNativeAccountsJob']['jobIds']) < 1:
        time.sleep(3)
        LOG.warning("Job not yet started, wait three seconds and try again")
        r = requests.post(graphurl, json=payload, headers=headers)

    LOG.warning("Job has now started")
    job_id = r.json()['data']['startRefreshAwsNativeAccountsJob']['jobIds'][0]['jobId']
    LOG.warning("Job ID is " + job_id + " - will now wait for exit status")

    # Wait for job to complete
    operation_name = "EventSeriesDetailsQuery"
    variables = {
    "activitySeriesId": job_id,
    "clusterUuid": "00000000-0000-0000-0000-000000000000"
    }
    payload = {
        "operationName": operation_name,
        "variables": variables,
        "query": JOB_MONITOR_QUERY
    }
    r = requests.post(graphurl, json=payload, headers=headers)
    status = r.json()['data']['activitySeries']['lastActivityStatus']
    task_complete_status = ["Success","Failure","Canceled"]
    while status not in task_complete_status:
        LOG.warning ("The status is " + status + " - sleeping for three and trying again")
        time.sleep(3)
        r = requests.post(graphurl, json=payload, headers=headers)
        progress = r.json()['data']['activitySeries']['progress']
        status = r.json()['data']['activitySeries']['lastActivityStatus']

    r = requests.post(graphurl, json=payload, headers=headers)
    status = r.json()['data']['activitySeries']['lastActivityStatus']
    LOG.warning("Job completed with status of " + status)

    return r

def assign_ec2_instance_to_sla(rubrik_instance, model, headers, graphurl):
    # Get SLA ID from name
    operation_name = "SLAListQuery"
    query = """query SLAListQuery($after: String, $first: Int, $filter: [GlobalSlaFilterInput!], $sortBy: SLAQuerySortByFieldEnum, $sortOrder: SLAQuerySortByOrderEnum, $showProtectedObjectCount: Boolean) {
  globalSlaConnection(
    after: $after
    first: $first
    filter: $filter
    sortBy: $sortBy
    sortOrder: $sortOrder
    showProtectedObjectCount: $showProtectedObjectCount
  ) {
    edges {
      node {
        name
        id
        __typename
      }
      __typename
    }
    pageInfo {
      endCursor
      hasNextPage
      hasPreviousPage
      __typename
    }
    __typename
  }
}"""
    variables = {
        "first": 20,
        "filter": [
        {
            "field": "NAME",
            "text": model.SLADomainName
        }
        ],
        "sortBy": "NAME",
        "sortOrder": "ASC"
    }

    payload = {
        "operationName": operation_name,
        "variables": variables,
        "query": query
    }
    r = requests.post(graphurl, json=payload, headers=headers)

    sla_id = (r.json()['data']['globalSlaConnection']['edges'][0]['node']['id'])
    LOG.warning("SLA Domain named " + model.SLADomainName + " has id of " + sla_id)
    existing_snapshots = True
    existing_snapshot_retention = None
    # Assign instance to sla
    operation_name = "AssignSlasForSnappableHierarchiesMutation"
    variables = {
        "existingSnapshotRetention": existing_snapshot_retention,
        "globalSlaAssignType": "protectWithSlaId",
        "globalSlaOptionalFid": sla_id,
        "objectIds": [
            rubrik_instance
        ],
        "shouldApplyToExistingSnapshots": existing_snapshots
    }
    query = """
        mutation AssignSlasForSnappableHierarchiesMutation($existingSnapshotRetention: ExistingSnapshotRetentionEnum, $globalSlaOptionalFid: UUID, $globalSlaAssignType: SlaAssignTypeEnum!, $objectIds: [UUID!]!, $applicableSnappableTypes: [SnappableLevelHierarchyTypeEnum!], $shouldApplyToExistingSnapshots: Boolean) {
        assignSlasForSnappableHierarchies(
            existingSnapshotRetention: $existingSnapshotRetention
            globalSlaOptionalFid: $globalSlaOptionalFid
            globalSlaAssignType: $globalSlaAssignType
            objectIds: $objectIds
            applicableSnappableTypes: $applicableSnappableTypes
            shouldApplyToExistingSnapshots: $shouldApplyToExistingSnapshots
        ) {
            success
            __typename
        }
        }
    """
    payload = {
        "operationName": operation_name,
        "variables": variables,
        "query": query
    }
    r = requests.post(graphurl, json=payload, headers=headers)
    return r

def get_secret(session, name,version=None):
    """Gets the value of a secret.

    Version (if defined) is used to retrieve a particular version of
    the secret.

    """
    secrets_client = session.client("secretsmanager")
    kwargs = {'SecretId': name}
    if version is not None:
        kwargs['VersionStage'] = version
    response = secrets_client.get_secret_value(**kwargs)
    return response


@resource.handler(Action.CREATE)
def create_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:
    # Typicaly model is in request.desiredResourceState
    model = request.desiredResourceState
    # Work-a-round to create a resource with no properties (and ignore any properties set)
    #model = ResourceModel(ID='',PolarisDomain='',PolarisUsername='',PolarisPassword='')
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.IN_PROGRESS,
        resourceModel=model,
    )
    try:
        LOG.warning("AWS Account id is " + model.AWSAccountId)
        secret = get_secret(session, "PolarisCredentials")
        LOG.warning("Secret username is " + json.loads(secret['SecretString'])['PolarisUsername'])

        # retrieve access token
        #access_token = retrieve_access_token(model.PolarisDomain, model.PolarisUsername, model.PolarisPassword)
        # setting up random primary identifier compliant with cfn standard
        #LOG.warning("recieved access token of " + access_token)
        headers, graphurl = retrieve_headers(session, model)
        #graphurl = 'https://' + model.PolarisDomain + '/api/graphql'

        # Get Rubrik ID of instance
        r = requests.post(graphurl,json={'query': LIST_ALL_INSTANCES_QUERY}, headers=headers)
        instances = r.json()['data']['awsNativeEc2Instances']['edges']
        filtered = [instance for instance in instances if instance['node']['instanceNativeId'] == model.EC2InstanceId]

        # Commented out below, but need to uncomment come prod
        # Need to implement error checking here
        if not filtered:
            # Nothing has been returned
            # do a refresh - MWP - Need to figure out account id!
            LOG.warning("Instance cannot be found within Rubrik Polaris, initiating account refresh")
            r = refresh_aws_account(model,headers,graphurl)

            LOG.warning("Trying to get machine again!")
            # error check status here
            # get filtered list again
            r = requests.post(graphurl,json={'query': LIST_ALL_INSTANCES_QUERY}, headers=headers)
            instances = r.json()['data']['awsNativeEc2Instances']['edges']
            filtered = [instance for instance in instances if instance['node']['instanceNativeId'] == model.EC2InstanceId]

            # may want to do error checking here to make sure it does exist the second time as well
            rubrik_instance_id = filtered[0]['node']['id']
            rubrik_instance_sla_name = filtered[0]['node']['effectiveSlaDomain']['name']
        else:
            rubrik_instance_id = filtered[0]['node']['id']
            rubrik_instance_sla_name = filtered[0]['node']['effectiveSlaDomain']['name']


        LOG.warning("Rubrik instance id is " + rubrik_instance_id)
        LOG.warning("Instance SLA Domain is " + rubrik_instance_sla_name)

        r = assign_ec2_instance_to_sla(rubrik_instance_id, model, headers, graphurl)


        r = requests.post(graphurl,json={'query': LIST_ALL_INSTANCES_QUERY}, headers=headers)
        instances = r.json()['data']['awsNativeEc2Instances']['edges']
        filtered = [instance for instance in instances if instance['node']['instanceNativeId'] == model.EC2InstanceId]
        rubrik_instance_id = filtered[0]['node']['id']
        rubrik_instance_sla_name = filtered[0]['node']['effectiveSlaDomain']['name']

        # Now let's issue the proper protect query
        model.ID = rubrik_instance_id
        model.SLADomainName = rubrik_instance_sla_name
        #progress.status = OperationStatus.SUCCESS
    except TypeError as e:
        # exceptions module lets CloudFormation know the type of failure that occurred
        raise exceptions.InternalFailure(f"was not expecting type {e}")
        # this can also be done by returning a failed progress event
        #return ProgressEvent.failed(HandlerErrorCode.InternalFailure, f"was not expecting type {e}")

    return ProgressEvent(status=OperationStatus.SUCCESS, resourceModel=model)


@resource.handler(Action.UPDATE)
def update_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:
    model = request.desiredResourceState
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.IN_PROGRESS,
        resourceModel=model,
    )

    LOG.warning("I can see an id of " + model.ID)
    LOG.warning("Will change SLA Domain to " + model.SLADomainName)
    headers, graphurl = retrieve_headers(session, model)
    #graphurl = 'https://' + model.PolarisDomain + '/api/graphql'

    r = assign_ec2_instance_to_sla(model.ID, model, headers, graphurl)

    return create_handler(session, request, callback_context)


@resource.handler(Action.DELETE)
def delete_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:
    model = request.desiredResourceState
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.SUCCESS,
        resourceModel=None,
    )
    return progress


@resource.handler(Action.READ)
def read_handler(
    session: Optional[SessionProxy],
    request: ResourceHandlerRequest,
    callback_context: MutableMapping[str, Any],
) -> ProgressEvent:
    model = request.desiredResourceState
    progress: ProgressEvent = ProgressEvent(
        status=OperationStatus.IN_PROGRESS,
        resourceModel=model,
    )
    model = request.desiredResourceState
    try:
        cfn = session.client('cloudformation')
        myself = cfn.describe_stack_resource(
            StackName=request.stackId.split(':')[5].split('/')[1],
            LogicalResourceId=request.logicalResourceIdentifier
            )["StackResourceDetail"]
        model.Content = json.loads(myself["Metadata"])['Content']

        headers, graphurl = retrieve_headers(session, model)
        #graphurl = 'https://' + model.PolarisDomain + '/api/graphql'

        r = requests.post(graphurl,json={'query': LIST_ALL_INSTANCES_QUERY}, headers=headers)
        instances = r.json()['data']['awsNativeEc2Instances']['edges']
        filtered = [instance for instance in instances if instance['node']['id'] == model.ID]
        rubrik_instance_id = filtered[0]['node']['id']
        rubrik_instance_sla_name = filtered[0]['node']['effectiveSlaDomain']['name']
        instance_id = filtered[0]['node']['instanceNativeId']
        model.ID = rubrik_instance_id
        model.SLADomainName = rubrik_instance_sla_name
        model.EC2InstanceId = instance_id
    except Exception as e:
        raise exceptions.InternalFailure(f"{e}")
    return ProgressEvent(
        status=OperationStatus.SUCCESS,
        resourceModel=model,
    )

# @resource.handler(Action.LIST)
# def list_handler(
#     session: Optional[SessionProxy],
#     request: ResourceHandlerRequest,
#     callback_context: MutableMapping[str, Any],
# ) -> ProgressEvent:
#     return ProgressEvent(
#         status=OperationStatus.SUCCESS,
#         resourceModels=[],
#     )