PROJECT IMPLEMENTATION BRIEF
Transform Existing Django Application into a Subscription-Based SaaS Product
1. Project Objective

We want to transform our existing Django application into a subscription-based product that multiple business owners can register for, pay to use, and independently configure.

IMPORTANT: This is an extension of our existing application, NOT a request to rebuild it.

The existing application already accepts contact details through a public form and forwards those details to a Telegram bot through an n8n workflow.

We want to retain the core functionality and extend it to support multiple independent business owners.

Our intended architecture is deliberately simple:

One Django application.
One shared database.
Multiple registered business owners.
Each business owner has a unique account ID.
Each business owner has their own Telegram configuration.
Each business owner gets a unique public form URL.
Each business owner manages their account through a private dashboard.
Their consumers can access and submit their public forms without authentication.
Access to the service is controlled by subscription payments through PayHero.

Do not introduce unnecessary infrastructure, microservices, separate frontend applications, or another multi-tenant platform.

Use the existing Django architecture, database, templates, models, and functionality wherever practical.

2. FIRST TASK: Inspect the Existing Project

Before modifying anything, thoroughly inspect the existing project.

Understand:

Current Django project structure.
Existing applications and their responsibilities.
Existing database models and relationships.
Existing public form implementation.
Existing form submission views and processing logic.
Current Telegram integration.
How n8n is currently integrated.
Existing URL patterns.
Existing templates and frontend styling.
Existing authentication functionality, if any.
Existing deployment configuration and environment variables.

Identify which existing components can be reused and which need modification.

Do not immediately start replacing existing files.

First establish how the current application works and prepare an implementation plan based on the actual codebase.

Preserve existing functionality unless a specific modification is required by this brief.

3. IMPLEMENTATION STEP 1: Introduce a Business Owner Dashboard

Create a dashboard for registered business owners.

The dashboard is intended exclusively for the people who purchase and manage our service.

Use Django templates and the existing frontend technologies.

Do not introduce React, Vue, or another frontend framework unless the project already depends on one and there is a compelling reason to retain it.

The dashboard should eventually contain:

A. Overview

Account information.
Account status.
Subscription status.
Subscription expiry date.
Number of form submissions, if submission tracking is available.
Quick access to configuration settings.

B. Telegram Configuration

Telegram bot token.
Telegram chat ID.
Configuration status.
Ability to save and update Telegram settings.
Ability to test the Telegram connection.

C. Public Form Settings

Display the business owner's unique public form URL.
Allow the owner to copy the URL.
Explain that this URL can be shared with their consumers.
Display the public form's status.

D. Account Settings

Business owner profile.
Email address.
Password management.

E. Billing

Current subscription plan.
Payment status.
Subscription expiry date.
Payment history.
Ability to renew or upgrade where applicable.

The initial objective is to establish the dashboard interface and its navigation. Connect the interfaces to actual backend functionality as the relevant implementation steps are completed.

4. IMPLEMENTATION STEP 2: Separate the Dashboard from the Public Form

This separation is fundamental.

We have TWO different audiences.

AUDIENCE A: BUSINESS OWNERS

These are our paying customers.

They need:

Registration.
Login.
Authentication.
Private dashboard.
Telegram configuration.
Subscription management.
Access to their public form URL.

AUDIENCE B: BUSINESS OWNERS' CONSUMERS

These are the people who visit the shared public form.

They need:

A publicly accessible form.
No registration.
No login.
No authentication.
No dashboard.
Ability to fill in contact details and submit.

The existing public form functionality should remain available.

Introduce a clean URL structure along these lines:

text
/                       Landing page
/register/              Business registration
/login/                 Business login
/dashboard/             Private dashboard
/dashboard/telegram/    Telegram configuration
/dashboard/billing/     Subscription management
/f/<uuid>/              Public customer form
/f/<uuid>/submit/       Public form submission
/pricing/               Pricing page


These are suggested routes. Adapt them to the existing project's URL conventions where appropriate.

The dashboard must require authentication.

The public form must NOT require authentication.

Do not accidentally apply login requirements to public form routes.

Both interfaces must operate within the same Django project and database.

5. IMPLEMENTATION STEP 3: Remove n8n and Integrate Telegram Directly

Currently, our submission flow is:

text
Public Form
    |
    v
Django Application
    |
    v
n8n Workflow
    |
    v
Telegram Bot


We want to remove n8n entirely.

The new flow should be:

text
Public Form
    |
    v
Django Application
    |
    v
Telegram Bot API
    |
    v
Business Owner's Telegram


Implement direct communication with the official Telegram Bot API from Django.

Create a reusable Telegram service/helper responsible for sending notifications.

The service should accept the relevant account configuration and submission details.

Requirements:

Retrieve the correct Telegram configuration for the business owner associated with the public form URL.
Send the submitted contact details to that owner's Telegram destination.
Handle Telegram API errors.
Handle invalid bot tokens and chat IDs.
Avoid exposing bot tokens in frontend code or application responses.
Avoid logging sensitive credentials.
Store Telegram credentials securely, preferably encrypted at rest.
Provide a way for business owners to test their Telegram configuration.

Do not hardcode a single Telegram bot configuration for all users.

Each business owner must have their own independent configuration.

If the existing submission workflow has useful validation or formatting logic, preserve and reuse it.

Store submissions before attempting notification delivery so a temporary Telegram failure does not destroy submitted contact information.

Remove n8n-related dependencies and configuration only after the replacement has been implemented and tested successfully.

6. IMPLEMENTATION STEP 4: Authentication, Business Owner IDs and Individual Configurations

Implement business owner authentication using Django's existing authentication capabilities.

Do not create a custom authentication system unnecessarily.

Each registered business owner must have:

A Django user account.
A unique internal account association.
An independent Telegram configuration.
A unique public identifier.
An associated subscription record.

Use the existing user model if appropriate. If a custom user model already exists, retain it.

If the project does not have a suitable user model, assess the safest approach before introducing one, especially if migrations or existing user data are involved.

Unique public identifiers

Each business owner must receive a unique, non-sequential public UUID.

For example:

text
Business Owner A: UUID-A
Business Owner B: UUID-B
Business Owner C: UUID-C


Use these identifiers to generate public form URLs.

Do not expose sequential database primary keys as public identifiers.

Account configuration

Create or extend the appropriate models to associate each business owner with their configuration.

A possible conceptual structure:

text
User
 |
 | One-to-one
 |
BusinessConfiguration
 |
 | One-to-one
 |
TelegramConfiguration

User
 |
 | One-to-one
 |
Subscription


Adapt this structure to existing models rather than duplicating existing functionality.

Security requirements:

Business owners must only access their own dashboard data.
Business owners must only update their own Telegram configurations.
Business owners must never access another owner's private settings or submissions.
Public UUIDs must identify form ownership but must not grant dashboard access.
Never trust an account ID submitted through a form body when the public URL already identifies the account.
7. IMPLEMENTATION STEP 5: Unique Public Form URLs and Account-Specific Notifications

This is one of the most important requirements.

Every business owner must receive an independently shareable public form URL.

Example:

text
https://yourplatform.com/f/uuid-a/
https://yourplatform.com/f/uuid-b/
https://yourplatform.com/f/uuid-c/


The public UUID determines which business owner's configuration is used.

Expected workflow:

Business Owner A registers.
Business Owner A configures their Telegram bot and chat ID.
Django generates Business Owner A's unique public form URL.
Business Owner A shares that URL with their consumers.
A consumer visits the URL.
The consumer fills in the existing contact form.
The consumer submits the form.
Django resolves the UUID from the URL.
Django identifies Business Owner A.
Django retrieves Business Owner A's Telegram configuration.
Django sends the contact details to Business Owner A's Telegram.

Repeat the same process independently for every business owner.

Critical requirement:

A submission through Business Owner A's URL must NEVER be sent to Business Owner B's Telegram.

Implement proper account isolation and test this explicitly.

The public form should retain the existing user experience as much as possible.

Consumers should not be aware of the underlying account management system.

They should simply visit the URL, fill in the form and submit.

8. IMPLEMENTATION STEP 6: PayHero Payments and Subscription Management

Integrate PayHero as our initial payment provider.

Inspect the current PayHero integration documentation before implementation.

Do not invent API endpoints, callback formats, authentication mechanisms or payment verification procedures.

Create the necessary payment and subscription models, reusing existing models where appropriate.

Subscription states

Support at least:

text
inactive
pending
active
expired
cancelled


Each subscription should be associated with one business owner.

Track relevant information, including:

Subscription plan.
Subscription status.
Payment reference.
Amount paid.
Payment date.
Subscription start date.
Subscription expiry date.

Payment workflow

Business owner visits the pricing page.
Business owner selects a subscription plan.
Django initiates a PayHero payment.
Customer completes the payment.
PayHero sends its payment callback/webhook.
Django validates the payment using PayHero's documented verification mechanism.
Django updates the payment record.
Django activates or extends the subscription.
Dashboard reflects the updated subscription status.

Important:

Do not activate subscriptions based only on a frontend success page.
Verify payment server-side.
Validate callback authenticity according to PayHero's documentation.
Make webhook processing idempotent.
Prevent duplicate payment callbacks from extending subscriptions multiple times.
Keep payment credentials in environment variables.
Record payment failures and pending payments appropriately.

Subscription enforcement

Restrict access when a subscription is inactive, expired or cancelled.

This restriction must be enforced server-side.

It must cover:

Dashboard access to protected functionality.
Telegram configuration changes where applicable.
Public form submissions.
Any other paid functionality.

Do not assume hiding dashboard elements is sufficient.

A consumer visiting an expired business owner's public URL should receive an appropriate message instead of having their submission processed.

The public URL itself should remain associated with the business owner, even when the subscription expires.

9. IMPLEMENTATION STEP 7: Pricing Page

Create a public pricing page using Django templates.

Initially support configurable subscription plans such as:

Monthly.
Quarterly.
Annual.

Do not hardcode pricing logic throughout the application.

Store plan information in an appropriate model or centralized configuration.

Each plan should have:

Plan name.
Price.
Duration.
Description.
Active/inactive status.

Allow business owners to select a plan and proceed to PayHero checkout.

The pricing page should be accessible without authentication.

10. IMPLEMENTATION STEP 8: Testing and Quality Assurance

Do not consider this project complete merely because the pages load.

Test the actual business workflows.

A. Authentication tests

Registration works.
Login works.
Logout works.
Unauthenticated visitors cannot access the dashboard.
Business owners cannot access other owners' private data.

B. Public form tests

Public URLs resolve correctly.
Forms work without authentication.
Existing form validation still works.
Submissions are stored correctly.
Invalid UUIDs return appropriate responses.

C. Telegram tests

Business Owner A's submissions reach Telegram A.
Business Owner B's submissions reach Telegram B.
Incorrect tokens are handled properly.
Failed Telegram delivery does not destroy submissions.
Credentials are never exposed.

D. Subscription tests

Active subscriptions permit submissions.
Pending subscriptions do not grant paid access.
Expired subscriptions cannot submit.
Duplicate payment callbacks do not cause duplicate subscription extensions.
Renewals extend subscriptions correctly.

E. Account isolation tests

This is mandatory.

Create at least two independent test accounts.

Submit through both public URLs.

Confirm that:

Account A only receives Account A's submissions.
Account B only receives Account B's submissions.
Neither account can access the other's configurations.
Neither account can access the other's dashboard data.

F. Regression tests

Confirm that the original form's essential functionality remains intact.

11. IMPLEMENTATION STEP 9: Deployment

Before deployment:

Review all database migrations.
Confirm environment variables are configured.
Remove obsolete n8n configuration after successful replacement.
Confirm HTTPS is enabled.
Verify production database configuration.
Verify static files and templates.
Configure appropriate logging.
Check payment callback URLs.
Test Telegram API connectivity.
Verify subscription enforcement.
Confirm that public URLs work in production.

Do not overwrite production data or perform destructive migrations without explicit approval.

12. STRICT DEVELOPMENT RULES

These rules apply throughout the project.

Work with the existing project, not against it.
Inspect before modifying.
Do not rebuild existing working functionality unnecessarily.
Do not introduce unnecessary technologies or infrastructure.
Do not create separate Django deployments for business owners.
Do not introduce unnecessary multi-tenant infrastructure.
Use Django's existing authentication and ORM capabilities.
Keep the consumer-facing public form independent of dashboard authentication.
Keep business owner configurations isolated.
Never expose private credentials.
Verify payments server-side.
Enforce subscription restrictions server-side.
Preserve existing functionality wherever possible.
Use database migrations rather than manually modifying production data.
Test each implementation phase before proceeding.

Development approach:

Work incrementally.

For each phase:

Inspect the relevant existing code.
Explain what needs to change.
Implement the changes.
Run relevant tests.
Report the files modified.
Report any issues or assumptions.
Confirm the phase is complete before proceeding.

Do not make large, unrelated changes across the project.

If an architectural decision conflicts with the existing codebase, explain the conflict and recommend the least disruptive solution before proceeding.

13. FINAL EXPECTED PRODUCT

At completion, we should have ONE Django application serving two distinct audiences.

Business owners:

Register and log in.
Access a private dashboard.
Configure their own Telegram bot.
Receive a unique public form URL.
Share that URL with consumers.
Receive submissions in their own Telegram.
Pay through PayHero.
Manage subscriptions.
Lose paid functionality when subscriptions expire.

Consumers:

Visit a business owner's unique public URL.
Access the existing contact form without authentication.
Fill in their contact details.
Submit the form.
Receive an appropriate submission confirmation.

Underlying architecture:

text
                DJANGO APPLICATION
                        |
          +-------------+-------------+
          |                           |
          v                           v
    BUSINESS OWNERS               CONSUMERS
          |                           |
    Authentication               Public URLs
          |                           |
    Private Dashboard             Public Forms
          |                           |
    Telegram Settings             Form Submission
          |                           |
    PayHero Payments                   |
          |                           |
          +-------------+-------------+
                        |
                        v
                SHARED DJANGO BACKEND
                        |
               UUID ACCOUNT RESOLUTION
                        |
               SUBSCRIPTION VALIDATION
                        |
               ACCOUNT CONFIGURATION
                        |
                        v
                TELEGRAM BOT API
                        |
                        v
             CORRECT BUSINESS OWNER


Final objective:

Turn our existing working Django application into a simple, maintainable, subscription-based product that can serve many independent business owners without unnecessarily complicating its architecture.

Preserve what already works. Extend what is needed. Avoid rebuilding what isn't broken.