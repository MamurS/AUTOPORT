# AutoPort Backend - Production Setup Guide

This guide will help you configure the AutoPort backend for production deployment with real API endpoints and services.

## Prerequisites

1. **SMS Service Account**: Sign up for [Eskiz SMS](https://notify.eskiz.uz/) service
2. **Email Service**: Configure SMTP credentials (Gmail, SendGrid, etc.)
3. **Database**: PostgreSQL database instance
4. **Domain**: SSL certificate for your domain

## Required Environment Variables

Create a `.env` file in the project root with the following variables:

### Application Settings
```bash
ENVIRONMENT=production
DEBUG=false
```

### Database Configuration
```bash
DATABASE_URL=postgresql+asyncpg://username:password@hostname:port/database_name
```

### Security Keys (REQUIRED - Generate Strong Keys)
```bash
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=your-production-jwt-secret-key-256-bits-long
SECRET_KEY=your-production-secret-key-256-bits-long
```

### SMS Service (ESKIZ SMS - REQUIRED)
```bash
# Get from https://notify.eskiz.uz/
SMS_API_TOKEN=your-eskiz-api-token
SMS_FROM_NUMBER=4546
SMS_API_URL=https://notify.eskiz.uz/api
```

### Email Service (REQUIRED for Admin MFA)
```bash
# For Gmail (recommended to use App Passwords)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
SMTP_FROM_EMAIL=noreply@autoport.uz
SMTP_FROM_NAME=AutoPort
SMTP_USE_TLS=true
```

### Frontend URLs
```bash
FRONTEND_URL=https://autoport.uz
ADMIN_FRONTEND_URL=https://admin.autoport.uz
```

### CORS Configuration
```bash
BACKEND_CORS_ORIGINS_STR=https://autoport.uz,https://admin.autoport.uz
```

## Production Validation

The application will validate that all required services are properly configured when running in production mode:

1. **SMS Service**: Validates `SMS_API_TOKEN` is set
2. **Email Service**: Validates `SMTP_PASSWORD` is set  
3. **Security Keys**: Ensures default keys are changed
4. **Environment**: Confirms production environment settings

## Setting Up SMS Service (Eskiz)

1. Go to [https://notify.eskiz.uz/](https://notify.eskiz.uz/)
2. Create an account and verify your business
3. Get your API token from the dashboard
4. Add the token to your `.env` file:
   ```bash
   SMS_API_TOKEN=your-token-here
   ```

## Setting Up Email Service

### Option 1: Gmail with App Passwords (Recommended)
1. Enable 2-factor authentication on your Gmail account
2. Generate an App Password:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate password for "Mail"
3. Use the generated password:
   ```bash
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=generated-app-password
   ```

### Option 2: SendGrid
```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=your-sendgrid-api-key
```

## Deployment Steps

1. **Clone Repository**
   ```bash
   git clone https://github.com/MamurS/autoport-backend.git
   cd autoport-backend
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your production values
   ```

4. **Run Database Migrations**
   ```bash
   alembic upgrade head
   ```

5. **Create First Admin** (Only on first deployment)
   ```bash
   python cli_admin.py bootstrap
   ```

6. **Start Application**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

## Production Checklist

- [ ] SMS service configured and tested
- [ ] Email service configured and tested
- [ ] Database migrations applied
- [ ] SSL certificate configured
- [ ] Environment variables set
- [ ] Admin account created
- [ ] Logs directory created
- [ ] Health checks working
- [ ] CORS properly configured
- [ ] Rate limiting enabled

## Testing Production Services

### Test SMS Service
```bash
curl -X POST "your-domain.com/api/v1/auth/register/request-otp" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+998901234567"}'
```

### Test Email Service
1. Try admin login to trigger MFA email
2. Check logs for email delivery status

### Test Health Endpoint
```bash
curl "your-domain.com/api/v1/health"
```

## Monitoring and Logs

- Application logs: Check for "Production Ready" status messages
- SMS delivery: Monitor Eskiz dashboard for delivery rates
- Email delivery: Check SMTP provider logs
- Database: Monitor connection pool and query performance

## Security Recommendations

1. **Use HTTPS only** in production
2. **Regularly rotate** API keys and secrets
3. **Monitor** failed login attempts
4. **Enable** admin account lockouts
5. **Use** strong, unique passwords
6. **Implement** IP whitelisting if possible
7. **Regular** security updates

## Troubleshooting

### SMS Not Sending
1. Check `SMS_API_TOKEN` is correct
2. Verify Eskiz account has sufficient balance
3. Check phone number format (+998...)
4. Review application logs for SMS errors

### Email Not Sending
1. Verify SMTP credentials
2. Check if using App Password (for Gmail)
3. Ensure SMTP port is not blocked
4. Review email service provider logs

### Database Connection Issues
1. Verify `DATABASE_URL` format
2. Check database server accessibility
3. Ensure database user has proper permissions
4. Test connection with direct database client

## Support

For technical support:
- Check application logs first
- Review this setup guide
- Contact your system administrator
- Submit issues to the repository

Remember: Never commit sensitive information like API keys or passwords to version control! 