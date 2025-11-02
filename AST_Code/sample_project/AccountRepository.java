package com.example.repo;

import com.example.util.Database;
import com.example.util.Helper;

public class AccountRepository {
    public void save(String accountId) {
        Helper.log("Saving account " + accountId);
        Database.execute("INSERT INTO accounts (id) VALUES ('" + accountId + "')");
    }
}
