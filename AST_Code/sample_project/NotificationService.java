package com.example.comm;

import com.example.comm.EmailService;

public class NotificationService {
    private EmailService email = new EmailService();

    public void notifyUser(String id) {
        email.sendWelcome(id);
    }
}
