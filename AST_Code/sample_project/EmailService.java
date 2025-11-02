package com.example.comm;

import com.example.util.Helper;

public class EmailService {
    public void sendWelcome(String userId) {
        Helper.log("Sending welcome email to " + userId);
    }
}
