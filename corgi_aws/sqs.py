import click
import logging
import boto3
import uuid
import json

client = boto3.client('sqs')
logger = logging.getLogger(__name__)


@click.group(help="Utils for SQS")
def sqs():
    pass

@sqs.command(help="Send test message to FIFO queue")
@click.option('--queue-url', '-q', help='The URL of the Amazon SQS queue to which a message is sent.', required=True)
@click.option('--number', '-n', default=1, type=int, help='Number of messages', show_default=True)
def send_message(queue_url, number):
    group_id = str(uuid.uuid4())
    for i in range(number):
        deduplication_id = str(uuid.uuid4())
        message = {
            'group-id': group_id,
            'seq': i,
        }
        response = client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message),
            MessageGroupId=group_id,
            MessageDeduplicationId=deduplication_id,
        )
        logger.info(f"Send message response: {response}")
        md5 = response['MD5OfMessageBody']
        message_id = response['MessageId']
        seq_num = response['SequenceNumber']
        req_id = response['ResponseMetadata']['RequestId']
        print(f'=> Message ID: {message_id}')
        print(f'   MD5:        {md5}')
        print(f'   Sequence:   {seq_num}')
        print(f'   Request ID: {req_id}')


def _ack_message(queue_url, handle):
    logger.info(f'Deleting message, handle: {handle}')
    try:
        client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=handle
        )
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")


@sqs.command(help="Receive test message from FIFO queue")
@click.option('--queue-url', '-q', help='The URL of the Amazon SQS queue from which a message is received.', required=True)
def receive_message(queue_url):
    while True:
        response = client.receive_message(
            QueueUrl=queue_url,
            WaitTimeSeconds=20,
            MaxNumberOfMessages=10,
            VisibilityTimeout=120,
        )
        logger.info(f"Receive message response: {response}")
        messages = response.get('Messages')
        if not messages:
            continue
        for message in messages:
            message_id = message['MessageId']
            body = message['Body']
            handle = message['ReceiptHandle']
            print(f'<= Message ID: {message_id}')
            print(f'   Body: {body}')
            _ack_message(queue_url, handle)
